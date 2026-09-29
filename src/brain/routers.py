"""Every router the application mounts after the build tracker's, one import line each.

**A router is mounted by being imported here, and nothing else lists it.** `ROUTERS` is read
off this module's own names, so a package that adds a router adds one import line, which ruff's
import sorting places by the module's name, and edits nothing another package edits unless the
two names sort next to each other. Rejected: an `include_router` line per package at the end of
`brain.app.create_app`, which is what this was until 2026-09-29. Every package appended at the
same place, so any two console pull requests conflicted there whatever they built.

**The order they are mounted in is their names', and it cannot change what a request reaches.**
Starlette takes the first route that matches, so mount order decides an address two routers
both answer, and nothing else. No two do: `tests/unit/test_routers.py` reads every route of
every router and refuses two that could match one request, which is what makes sorting safe
and keeps it safe. The build tracker's router is not here, because `brain.app` mounts it first
and after `mount_console_entry`, and the console fallback stays last, as both require.

**Imported, not discovered.** Finding every `*_routes` module at start-up would drop even the
one line, and was rejected because `brain.ops.application_privileges` reads what runs as the
application role from the static imports of `brain.app`: a router found at run time would run
as `brain_app` and be invisible to the check that its tables are granted.
`tests/unit/test_routers.py` instead refuses a `*_routes` module that is not imported here, so
forgetting the line fails a test rather than leaving a screen unanswered.

The comment above each import was written beside its `include_router` line in `brain.app`, in
the order the packages landed, which is what its ordinals and its "above" refer to.

Task ids: none
"""

from collections.abc import Mapping
from typing import Final

from fastapi import APIRouter

# The install acceptance checks' results for the commit this serves: passed, failed or not
# run, public and read-only like deploy-checks. See `brain.acceptance_routes`.
from brain.acceptance_routes import router as acceptance_router

# Asking for access: one constant reply to the asker, and the owner's own list, which is how
# a request is delivered. See `brain.access_request_routes`.
from brain.access_request_routes import router as access_request_router

# One agent's About tab, which reads the agent's automations and so cannot sit on the
# workspace's router without an import cycle. The same audience and the same one 404.
from brain.agent_about_routes import router as agent_about_router

# One agent's Artifacts section: its list, a download re-checked at the requester's reach, a
# supersession or an archive as a row, and the latest of a kind for a client.
from brain.agent_artifact_routes import router as agent_artifact_router

# New agent and Edit as a draft: the builder's form, drafts saved as revisions, checked,
# rehearsed and published, and the second person a wider publish waits for. See
# `brain.agent_builder_routes`.
from brain.agent_builder_routes import router as agent_builder_router
from brain.agent_capability_routes import router as agent_capability_router

# Enabling, disabling, archiving, handing on and duplicating an agent, and installing a
# published template version. Its own router because these are writes and the agent router
# above is the page's read: an `admin:` authority asked before the agent is read, its
# audience, a precondition the page drew, and a row whose trigger writes the ledger entry.
# One agent's Conversations section: the reader's own threads it answered in, with who answered
# and how each run ended, a failed one included.
from brain.agent_conversation_routes import router as agent_conversation_router

# One agent's leash: its rungs as they stand, every move with its evidence, a verdict that the
# breaker reads, and the supervision pin and its reviews.
from brain.agent_leash_routes import router as agent_leash_router
from brain.agent_lifecycle_routes import router as agent_lifecycle_router
from brain.agent_memory_routes import router as agent_memory_router

# An agent's pinned provider and model, tried before its tier. See `brain.agent_model_routes`.
from brain.agent_model_routes import router as agent_model_router

# The agent roster and one agent's workspace. A fourth router because the refusal differs
# again: who may see an agent is its audience rather than a capability, and a hidden agent
# and a missing one are one answer. The same `asking` dependency, imported.
from brain.agent_routes import router as agent_router
from brain.agent_workspace_routes import router as agent_workspace_router

# Mounted here and nowhere else. An unmounted router is the failure this repository keeps
# finding, and the timeout middleware in `brain.app` is the most recent one.
from brain.api_routes import router as api_router

# The approvals queue and one approval's card. A fifth router because the refusal differs
# again: who is offered an approval is `pending_for` over the action's own row, and an
# approval out of reach, decided, lapsed or missing is one answer. GET only; see the module.
from brain.approval_routes import router as approval_router

# The Artifacts screen. A list only when something attached records what an agent produced,
# and a sentence saying nothing does until then. See `brain.artifact_routes`.
from brain.artifact_routes import router as artifact_router

# The Audit screen, the Govern section's last item in `docs/screens.html`. A router of its own
# because what it reads is the ledger, where every row is decided one at a time by
# `brain.audit.view.AuditView` and a page is filled from what survives. See
# `brain.audit_routes`.
from brain.audit_routes import router as audit_router

# The automation gallery on an agent's Automations tab, and its one confirmed install. Its own
# router because the write is: an `admin:` authority asked before the agent is read, a
# confirmation recomputed on the server, and a row whose trigger writes the ledger entry.
from brain.automation_gallery_routes import router as automation_gallery_router

# The endpoint an automation step calls. A sixth router because the caller differs: it
# authenticates an automation's credential rather than a person's token, and runs as the
# automation's owner. It does not take `asking`, and `asking` does not take its credential.
from brain.automation_routes import router as automation_router

# An agent's installed automations, their runs, and the confirmed start and stop. Its own
# router for the gallery's reason: an authority asked before anything is read, a confirmation
# recomputed on the server, and a row whose trigger writes the ledger entry.
from brain.automation_schedule_routes import router as automation_schedule_router

# The Automations module: every automation a reader may see, one automation's page and
# figures, and the confirmed pause, resume, schedule change, removal and adoption.
from brain.automations_routes import router as automations_router

# Binding a chat account with a one-time code minted in My workspace, unbinding it, and the
# Channels screen's bindings and health behind the channel's own authority. See
# `brain.binding_routes`.
from brain.binding_routes import router as binding_router

# The access certification report, taken from the Access review screen and recorded on the
# Exports log before it is handed over. See `brain.certification_export_routes`.
from brain.certification_export_routes import router as certification_export_router

# Channels: the one address every vendor posts a message to, which takes no caller and proves
# the signature, and each channel's record, switch, test message and deliveries behind the
# connector authority over `<channel>_channel`. See `brain.channel_routes`.
from brain.channel_routes import router as channel_router

# The document a citation on Ask links to, its passages at the reader's reach through the
# handler and policy the answer used. See `brain.cited_document_routes`.
from brain.cited_document_routes import router as cited_document_router

# Field-level classification. A third router for the reason there is a second: the rules
# differ again. This one answers about the policy over a document's columns rather than
# about its rows, it takes no session because there is nothing stored to read, and its
# write verb is `admin` rather than `write` because what it governs is what other people
# may see. The same `asking` dependency, imported rather than re-declared.
from brain.classification_routes import router as classification_router

# The Compliance screen: a sensitive topic's named person and the referrals routed to them, the
# processing register per connector, and breach cases with the PDPA clock, behind
# `admin:compliance` over everything. See `brain.compliance_routes`.
from brain.compliance_routes import router as compliance_router

# The connectors screen. A router of its own because what it answers about is which outside
# systems this company reads, where the name itself is the disclosure: the list is narrowed
# by the reader's own grant and a refusal names nothing. Connecting and disconnecting a source
# are its two writes, under `admin:connector` over that source, and what connecting does not do
# yet is served beside the list. See `brain.connector_routes`.
from brain.connector_routes import router as connector_router

# The landing screen's figure row: how the last seven days' requests ended and what they cost,
# each at the reader's basis. See `brain.console_overview_figures_routes`.
from brain.console_overview_figures_routes import router as console_overview_figures_router
from brain.console_overview_routes import router as console_overview_router

# One entity's figures on its detail page, each behind the question its list screen asks, and
# the landing screen's health strip and Needs you. See `brain.console_stats_routes` and
# `brain.console_overview_routes`.
from brain.console_stats_routes import router as console_stats_router

# Setting a credential, and seeing which are held. Beside the wizard because the wizard's
# provider key is kept through the same store, and a router of its own because its subject is
# the one value no other route may carry: it writes into the vault, answers that a secret is
# held and when, and is built on `brain.api.NoEchoRoute` so not even a refused body is
# repeated. See `brain.credential_routes`.
from brain.credential_routes import router as credential_router

# The data steward: who every read of the company's data begins with, and naming one on an
# install whose setup named nobody, behind `admin:data_steward` over everything. See
# `brain.data_steward_routes` and `brain.identity.data_steward`.
from brain.data_steward_routes import router as data_steward_router

# Import and export: what the code can move and whether an install can move it now, and the
# audit trail export, recorded in the ledger before the document is handed over. See
# `brain.data_transfer_routes`.
from brain.data_transfer_routes import router as data_transfer_router

# Send the evening digest to: the one setting naming a connected channel and a conversation in it,
# chosen from what each channel offers now and saved as the Settings screen saves. See
# `brain.digest_routes`.
from brain.digest_routes import router as digest_router

# Every person this install knows, one person's page, and a person added by hand where no staff
# list is read (M27.11.2, M27.15.19). See `brain.directory_routes`.
from brain.directory_routes import router as directory_router

# What the Retention screen needs beside the report: who may act, what each act does in the
# words a confirmation shows, the export log, and the erasure queue with its one write, which
# files a request the worker's queue carries out. See `brain.erasure_routes`.
from brain.erasure_routes import router as erasure_router

# Errors: the failed jobs and failed requests the database keeps, each behind the decision
# that already says who may see it, and a field saying the process log is kept nowhere the
# console can read. See `brain.error_routes`.
from brain.error_routes import router as error_router

# A question nothing answered, handed to the person named for its skill's queue, the caller's two
# lists of them, and the naming form. See `brain.escalation_routes`.
from brain.escalation_routes import router as escalation_router

# The Knowledge, Learning and Memory screens. A router of its own because all three are the
# estate-wide reads `brain.console.govern_estate` decides, and all three stand on a store
# that is empty on every install today: each response says which of its facts has no source
# rather than drawing an empty table that reads as a company with nothing in it. No write.
# See `brain.estate_routes`.
from brain.estate_routes import router as estate_router

# Features: which genuinely new features this install has switched on, and the switch, behind
# `admin:feature` over everything. See `brain.feature_routes` and `brain.ops.features`.
from brain.feature_routes import router as feature_router

# Assigning a capability pack, and the Approver misconfiguration flag on the Roles screen.
# Every grant a pack means goes through the same authority a single grant does. See
# `brain.govern_pack_routes`.
from brain.govern_pack_routes import router as govern_pack_router

# Departments and teams, Elevation, Access review and Subscribers, beside People in Govern. A
# router of its own because one of its four is the only write that records a review decision,
# and two of its screens say what the install does not store rather than drawing an empty
# list. See `brain.govern_people_routes`.
from brain.govern_people_routes import router as govern_people_router

# Who holds each role, and appointing, deputising and removing one. See
# `brain.govern_role_routes`.
from brain.govern_role_routes import router as govern_role_router

# The four Govern screens, and the two writes over a grant. A router of its own because
# what it answers about is the permission system itself: whether a screen opens is
# `brain.console.reads.permitted` rather than a bare capability, so an existence-only
# reader is refused a configuration screen, and the two writes defer entirely to
# `brain.console.scoped_authority` and `brain.console.govern`. See `brain.govern_routes`.
from brain.govern_routes import router as govern_router

# Which identity-provider group confers which role, on the Roles screen, and what the sync
# has written from them. See `brain.group_rule_routes`.
from brain.group_rule_routes import router as group_rule_router

# Stop: what is stopped, stop at once, and resume with a written reason, behind `admin:halt` in
# a scope that matches what is stopped. See `brain.halt_routes` and `brain.ops.halt_store`.
from brain.halt_routes import router as halt_router

# The five install screens. A ninth router because what it answers about is the deployment
# rather than the company's data: no name to guess, no row belonging to anybody, and no
# session on four of the five. The same `asking` dependency, imported. See
# `brain.install_routes`.
from brain.install_routes import router as install_router

# Scheduled jobs beside Live runs: how each job last went, and pause, resume and run now as
# rows the worker's tick reads. Read for everybody and narrowed per job; the controls need
# `admin:schedule` over everything and the `schedule_control` feature. See `brain.jobs_routes`.
from brain.jobs_routes import router as jobs_router

# Adding a web page by its link, and a bulk upload queued for the worker to read (M7.1.2,
# M7.1.5). See `brain.knowledge_intake_routes`.
from brain.knowledge_intake_routes import router as knowledge_intake_router

# A stored document verified, handed over, replaced and proposed for the whole company, the
# tasks each opens and captured solutions decided. See `brain.knowledge_lifecycle_routes`.
from brain.knowledge_lifecycle_routes import router as knowledge_lifecycle_router

# Whether a document is public for the website widget, read and changed from its detail page by a
# person whose grant decides it for that document's department. See `brain.knowledge_public_routes`.
from brain.knowledge_public_routes import router as knowledge_public_router

# Adding a document to the knowledge layer from the Knowledge page, read by the text path and
# placed where the uploader holds `admin:knowledge`. See `brain.knowledge_routes`.
from brain.knowledge_routes import router as knowledge_router

# Connect Lark: the steps, a read-only test and switching its uses on. See
# `brain.lark_connect_routes`.
from brain.lark_connect_routes import router as lark_connect_router

# Logs: the warnings and errors this install kept, redacted on their way in, searchable and
# paged, behind `admin:application_log` over everything. See `brain.log_routes`.
from brain.log_routes import router as log_router

# My workspace, the member screen `home`: what the person asking has asked, kept and been
# given, gated on the member grant and on nothing administrative. See `brain.mine_routes`.
from brain.mine_routes import router as mine_router

# A tier's window and headroom, and residency constraints. See `brain.model_health_routes`.
from brain.model_health_routes import router as model_health_router

# Which console a reader is given: the company console, or a department's with the menu
# SCREEN 2 draws narrowed to what they hold. Decided from grants at the admitted reach, so
# the shell renders an answer rather than a permission check of its own. See
# `brain.navigation_routes`.
from brain.navigation_routes import router as navigation_router

# Notifications: every notice this product composes, who is told what and whether anything
# sends it, the switch that stops one, and the email relay with its password in the vault and
# a test message, behind `admin:notification` over everything. See
# `brain.notification_routes`.
from brain.notification_routes import router as notification_router

# Live runs and Models and health, the two Operate screens `docs/screens.html` draws beside
# the overview. A router of its own because its two refusals differ from every router above:
# live runs narrows row by row and refuses nobody, and the models answer is whole-install and
# refuses a reader who could not see everybody's. See `brain.operate_routes`.
from brain.operate_routes import router as operate_router

# The interrupted actions: every side effect a stopped worker left unconfirmed and what the
# recovery sweep learnt about it, for a reader who may see that sweep. See `brain.operation_routes`.
from brain.operation_routes import router as operation_router

# Disabling a person and enabling them again, from the Departments and teams screen, behind the
# grant decision in a scope admitting their row. See `brain.principal_state_routes`.
from brain.principal_state_routes import router as principal_state_router

# Prompts: the system instructions every agent is given, shown and never edited, and each
# agent's own instructions, edited as a local change to its template. See
# `brain.prompt_routes`.
from brain.prompt_routes import router as prompt_router

# The provider registry: terms and lane overrides recorded, an OpenAI-compatible provider
# added with its key written to the vault first, and the register exported. See
# `brain.provider_registry_routes`.
from brain.provider_registry_routes import router as provider_registry_router

# Models and providers: every provider this install can call, switched on and off behind
# `admin:routing_matrix` over everything, the ladder as the next call will walk it with each
# rung's measured health, and a metered check. See `brain.provider_routes`.
from brain.provider_routes import router as provider_router

# Who can see a record, for somebody who can already see it. See `brain.record_access_routes`.
from brain.record_access_routes import router as record_access_router

# The three Report screens: service levels, spend and adoption. A router of its own because
# the decision differs again and in the opposite direction to the matrix's: none of these
# checks a capability at all, because the module that owns each screen narrows it row by
# row and a check here would be the first half of that predicate in a second copy. See
# `brain.report_routes`.
from brain.report_routes import router as report_router

# The Requirement checks screen: the register's rows by area and what a person saw each do on
# this install, recorded. See `brain.requirement_check_routes`.
from brain.requirement_check_routes import router as requirement_check_router

# The Resolution review screen: the pairs entity resolution could not settle, and a reviewer's
# merge or rejection, behind `admin:entity_merge` over everything and the reach of both records.
# See `brain.resolution_routes` and `brain.resolution.review_store`.
from brain.resolution_routes import router as resolution_router

# The retention report and the four writes that decide whether the sweep acts. A router of
# its own because two of its writes are the only way a deletion is approved or suspended:
# every write needs its authority over everything, and the report is shown whole to a
# company-wide reader and to nobody else. See `brain.retention_routes`.
from brain.retention_routes import router as retention_router

# A followed citation's place, kept for the learning signal, and the signal read by a knowledge
# administrator. Never a document, a question or a person. See `brain.retrieval_routes`.
from brain.retrieval_routes import router as retrieval_router

# The routing matrix. A second router rather than more routes on the first, because the
# rules differ: `api_routes` answers about entities, where the name itself is enumerable,
# and this one answers about the model chain, where it is not. Both take the same
# `asking` dependency, which `api_routes` declares once and this imports.
from brain.routing_routes import router as routing_router

# Service accounts: an integration registered at its owner's reach, a key shown once, and both
# taken away, behind `admin:credential`. See `brain.service_account_routes`.
from brain.service_account_routes import router as service_account_router

# Sessions and sign-in links, beside People in Govern, and the two controls that end a session
# and unlink an account. See `brain.session_routes`.
from brain.session_routes import router as session_router

# Settings, under Install: every installation value with where it came from, and branding
# saved, behind `admin:install_setting` over everything. See `brain.settings_routes`.
from brain.settings_routes import router as settings_router

# The setup wizard's appointment, which runs `apply_install` and appoints the first
# administrator the finishing screen above then signs in. An eighth router because its caller
# holds the setup code and no token at all. See `brain.setup_routes`.
from brain.setup_routes import router as setup_router

# The wizard's staff list screen: what to register, where to sign in, and one read of the
# list, each behind the setup code the appointment asks for. See `brain.setup_staff_routes`.
from brain.setup_staff_routes import router as setup_staff_router

# Binding a Keycloak subject to a principal. A seventh router because it has two callers:
# an administrator over everything under the prefix, through `asking`, and the setup
# wizard's finishing screen at /setup/sign-in, which takes the setup code and a verified
# token and no `asking`, and closes once anybody signs in. See `brain.sign_in_routes`.
from brain.sign_in_routes import router as sign_in_router

# The Skills screen, SCREEN 6 of `docs/screens.html`. A router of its own because what it
# answers about is neither a grant nor an agent: it is the skill library, its review queue and
# the procedures the agents a reader may see are pinned to. Its three writes add a skill,
# decide about one as somebody other than who added it, and assign an approved one through
# `attach_skill`, each asking its `admin:` authority first. See `brain.skill_routes`.
from brain.skill_routes import router as skill_router

# The Staff sources screen and the trial run behind it. A router of its own because it
# refuses nobody on its listing: a source sits at `brain.console.govern.NOWHERE`, so the
# answer for a reader who reaches none of them is the empty page rather than the refusal
# the four govern screens make, and refusing instead would let a caller read off whether
# somebody else holds a capability. See `brain.staff_source_routes`.
from brain.staff_source_routes import router as staff_source_router

# What the signed-in person is told as a steward: grants people made to themselves that reach a
# document, source or agent they answer for. See `brain.stewardship_routes`.
from brain.stewardship_routes import router as stewardship_router

# Storage: the buckets the product keeps, each one's retention and why, and where the store
# is, behind `admin:storage` over everything. Never an object's name. See
# `brain.storage_routes`.
from brain.storage_routes import router as storage_router

# A person's own threads, listed, searched and reopened at the reach held now. See
# `brain.thread_routes`.
from brain.thread_routes import router as thread_router

# The Tools screen: every tool with what it needs and does, and the switch that stops one for
# the install or one department's people, behind `admin:tool`. See `brain.tool_routes`.
from brain.tool_routes import router as tool_router

# One run's stored trace, read under the payload role the caller's own token carries, with the
# read on record before it happens. See `brain.trace_routes`.
from brain.trace_routes import router as trace_router

# Every budget and request window a person may set from the Rate limits screen, within the
# product's bounds, and one set, behind `admin:install_setting`. See `brain.tuning_routes`.
from brain.tuning_routes import router as tuning_router

# The Secrets vault screen: the seal, every slot, each source's leases and the audit log's
# shipping. Read only, under the credentials route's capability. See `brain.vault_routes`.
from brain.vault_routes import router as vault_router

# Webhooks: every subscriber, where it points, whether its signing secret is held and its
# recent outcomes, and registering, replacing a secret and switching off behind
# `admin:webhook_subscriber`. Built on `NoEchoRoute`, because two of its writes carry a
# secret. See `brain.webhook_routes`.
from brain.webhook_routes import router as webhook_router

# The website widget's front door: a stranger's browser is handed a session, or told why not, and
# its questions are answered from knowledge marked public alone, with no sign-in and the origin
# proved instead. See `brain.widget_routes`.
from brain.widget_routes import router as widget_router


def routers_in(namespace: Mapping[str, object]) -> tuple[APIRouter, ...]:
    """Every router a module's namespace holds, in the order of the names they are held under."""
    return tuple(value for _, value in sorted(namespace.items()) if isinstance(value, APIRouter))


#: Every router imported above, in the order of the names they are imported as.
ROUTERS: Final[tuple[APIRouter, ...]] = routers_in(globals())
