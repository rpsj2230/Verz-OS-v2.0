<!-- Generated from docs/wbs/acts.js by brain.migration.checklist. Do not edit: run `uv run python -m brain.migration.checklist` instead. -->

# Delivery checklist

Work in the plan that no commit can close. Every item here is done by a person, on the week of a migration, with a client. They are counted separately from the build for that reason: the percentage on the build page measures work that closes by being written, and these do not.

47 items, 7 of which gate the cutover.

**The items marked GATES CUTOVER are refused rather than listed.** `brain.migration.decommission` will not report a completed cutover while any of them is unrecorded, because their absence has a security consequence and a list nothing gates is a list nobody reads.

**The items marked NOT CODE HERE could not be built by anybody in this repository.** They name one company's own things, and the first rule of this repository is that no company's details go into it. They are recorded rather than left looking undone, so nobody spends a day trying to make them fit.

## M0 Foundation and repository

### M0.1 Repository and tooling

- [ ] `M0.1.1` Private GitHub repo, branch protection, CODEOWNERS on the three core files
  - owner's decision 2026-09-21: the repository stays public on purpose for now and he makes it private and protects main himself before go-live; not to be raised again until then

## M30 Hosting, delivery and recovery

### M30.6 Found by tracing every requirement to a task

- [ ] `M30.6.3` The company sets its own time targets in seconds for first output and for a complete answer in each lane before go-live, and they are recorded as the targets the service levels screen measures against

## M37 Migration, launch and handover

### M37.2 Replacing AnyGen

#### M37.2.1 What is actually in there

- [ ] `M37.2.1.1` Inventory the twelve house skills, named individually, since each is authored work and not a setting **NOT CODE HERE**
  - the count and the names are one company's authored estate, and a product every client installs cannot hold them
- [ ] `M37.2.1.2` Inventory every agent with its connectors, skills, channels and availability, because an agent is a composition and not a prompt
- [ ] `M37.2.1.3` Inventory automations, which are owned by an agent there and will be owned by an agent here
- [ ] `M37.2.1.4` Export memory files, both curated and chat-extracted, with their change history
- [ ] `M37.2.1.5` List which Lark groups each agent is installed into, since that is what staff actually see **NOT CODE HERE**
  - one company's chat groups, named. The register that holds the answer is generic; the answer is not
- [ ] `M37.2.1.6` Record what AnyGen produced that anyone still relies on **NOT CODE HERE**
  - names the outgoing vendor and what it made for one company

#### M37.2.2 Skills come across, they are not rewritten

- [ ] `M37.2.2.1` Export verz-master-theme, verz-doc-letterhead, seo-audit and website-cro-audit first: they are in daily use and are the test of whether import works at all **NOT CODE HERE**
  - four of one company's skills by name. `brain.migration.skills` is the generic half and is built

#### M37.2.5 Cutover in Lark, where staff will notice

- [ ] `M37.2.5.1` Install alongside, in one group first, with both bots present
- [ ] `M37.2.5.2` Agreed period answering the same questions from both, with disagreements logged
- [ ] `M37.2.5.3` Announce the switch before removing their bot, not after
- [ ] `M37.2.5.4` Remove the AnyGen bot from each group in the agreed order **GATES CUTOVER**
  - a bot left in a group keeps receiving that group's messages. Removing the tenant installation is the authorisation half and this is the delivery half, and either one left undone leaves the outgoing vendor reading the client's internal chat
- [ ] `M37.2.5.5` Keep their bot reachable read-only for an agreed window in case something was missed

#### M37.2.6 Decommission a SaaS, which is not the same as a server

- [ ] `M37.2.6.1` Revoke every OAuth grant AnyGen holds - Gmail, Drive, Calendar, Sheets, Docs and the rest - because cancelling a subscription does not revoke them **GATES CUTOVER**
  - every grant is a live credential on somebody else's service and cancelling the subscription does not withdraw one. This is how an outgoing vendor keeps reading a client's mail after everybody believes the account is closed
- [ ] `M37.2.6.2` Remove the AnyGen app from the Lark tenant, not just from the groups **GATES CUTOVER**
  - a tenant installation is a tenant-level grant. Removing the app from every group removes what staff see and leaves the scopes it was installed with, which is the same failure as an unrevoked grant one layer up
- [ ] `M37.2.6.3` Export anything with retention value before the account closes, since access ends with billing
- [ ] `M37.2.6.4` Cancel the subscription only after the export is verified restorable
- [ ] `M37.2.6.5` Record the date access actually ended, which is a different date from the last invoice **GATES CUTOVER**
  - without it there is no evidence of when access ended, and the last invoice is the date everybody reaches for instead. It is the fact an incident review or an audit asks for, and it cannot be reconstructed afterwards

### M37.3 Pilot and rollout

#### M37.3.1 Pilot

- [ ] `M37.3.1.1` One department, agreed scope, named champion
- [ ] `M37.3.1.2` Twenty real questions as the acceptance set
- [ ] `M37.3.1.3` Daily review of every answer for the first week
- [ ] `M37.3.1.4` Explicit go or no-go decision with written criteria

#### M37.3.2 Departmental rollout

- [ ] `M37.3.2.1` Rollout order agreed with the client
- [ ] `M37.3.2.2` Per-department onboarding session
- [ ] `M37.3.2.3` Per-department starter questions and knowledge seeding

#### M37.3.3 Training

- [ ] `M37.3.3.1` Staff session: what it can see, how to ask, how to correct it
- [ ] `M37.3.3.2` Admin session: console walkthrough, grants, leashes, review queues
- [ ] `M37.3.3.3` Recorded and left with the client

### M37.4 Acceptance and commercial close

#### M37.4.1 Acceptance

- [ ] `M37.4.1.1` Acceptance criteria signed before build, not after
- [ ] `M37.4.1.3` Restore drill executed in front of the client **GATES CUTOVER**
  - a backup nobody has read back is a file, which is the refusal `brain.ops.recovery` already makes about the live system and `FinalBackup.verified` makes about the last copy of the old one. In front of the client is what makes it evidence rather than a claim, and the cutover is the last moment it can be asked for
- [ ] `M37.4.1.4` Security review completed if the client requires one
- [ ] `M37.4.1.5` Penetration test scheduled where contractually required

#### M37.4.2 Contract artifacts

- [ ] `M37.4.2.1` Data processing agreement
- [ ] `M37.4.2.3` Support and escalation procedure

### M37.6 Go-live hardening

#### M37.6.1 Administrative consoles

- [ ] `M37.6.1.1` Two-factor on the deployment control panel account, because its sign-in page answers from the internet and it holds every container, database and secret on the host **GATES CUTOVER**
  - a public sign-in page is fine when a guessed or stolen password is not sufficient on its own, and this one is not a console among others: it is the control plane for every container on the host, including the identity provider's own database and every environment variable in it. One credential between the internet and all of that is the single largest exposure on the box, and the fix is an authenticator scan
- [ ] `M37.6.1.2` Delete the temporary identity provider administrator created at bootstrap, so an internet-facing admin sign-in is one account to guess rather than two **GATES CUTOVER**
  - the same shape as the OAuth grants two groups up: a credential left behind after it has served its purpose, on a service reachable from outside. It is worse than an unused password because nothing about an unused admin account looks different on the day it is used
- [ ] `M37.6.1.4` Rotate the identity provider's bootstrap administrator password once the account it created has been deleted
  - conditional on the deletion above and much smaller once it is done: with the account gone the value signs into nothing. Not gated, for the reason the two conditional acceptance leaves are not gated either, and a gate that fires when it should not is a gate somebody switches off

### M37.7 Found by tracing every requirement to a task

- [ ] `M37.7.1` The company names its data steward on the people screen and the steward grants each pilot department's staff their starter reads, recorded in the audit trail
- [ ] `M37.7.2` The company switches on a second sign-in factor for every account on the identity provider's admin console and every other administrative console of the install, and records that each one asks for it
- [ ] `M37.7.3` The company's administrator creates the ticket desk and chat workspace credentials with the scopes the integration guide lists and enters them on the connectors screen, never in a file or a message
- [ ] `M37.7.4` The company's workspace administrator installs the product's chat app with the scopes the channel guide lists, adds it to the pilot groups and creates the directory app the staff source signs in with
- [ ] `M37.7.7` Commission a penetration test of the owner's install before the first company data is connected, and record each finding with its fix or accepted risk

## M38 Continuous delivery and live status

### M38.1 Pipeline, built in wave 0 so every wave can ship

#### M38.1.1 Laptop to GitHub

- [ ] `M38.1.1.5` CODEOWNERS forcing review on the gate, the redactor and the catalogue projection
  - owner's decision 2026-09-21: the repository stays public on purpose for now and he makes it private and protects main himself before go-live; not to be raised again until then

### M38.2 Deploy at the end of every wave

#### M38.2.1 Wave close ritual

- [ ] `M38.2.1.3` Deploy to production
  - the pipeline that does it is built, closed by the wave-zero milestone, and has deployed this repository all day. What is left is somebody deciding a particular release goes out on a particular day, which is the act, and no commit closes it
- [ ] `M38.2.1.4` Smoke test: one real question answered end to end by a real person
  - the leaf says a real person in as many words, and that is the whole content of it. A fixture asking the same question is the wave-one milestone, which is a different leaf and is buildable
- [ ] `M38.2.1.5` Restore drill from wave three onward
  - a drill is somebody restoring a real backup onto real hardware and timing it. The machinery it exercises is code and is the recovery screen leaf under M27; the drill is the act, and `brain.launch.service_level` already refuses to report a recovery figure that rests on a schedule rather than on a copy somebody made
