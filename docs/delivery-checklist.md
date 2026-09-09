<!-- Generated from docs/wbs/acts.js by brain.migration.checklist. Do not edit: run `uv run python -m brain.migration.checklist` instead. -->

# Delivery checklist

Work in the plan that no commit can close. Every item here is done by a person, on the week of a migration, with a client. They are counted separately from the build for that reason: the percentage on the build page measures work that closes by being written, and these do not.

33 items, 5 of which gate the cutover.

**The items marked GATES CUTOVER are refused rather than listed.** `brain.migration.decommission` will not report a completed cutover while any of them is unrecorded, because their absence has a security consequence and a list nothing gates is a list nobody reads.

**The items marked NOT CODE HERE could not be built by anybody in this repository.** They name one company's own things, and the first rule of this repository is that no company's details go into it. They are recorded rather than left looking undone, so nobody spends a day trying to make them fit.

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
