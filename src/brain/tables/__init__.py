"""Every table in the system. Until this package existed there were none.

Everything this platform enforces was, before now, a rule about objects in memory: a
`Principal` that had to be constructed correctly, an `EntitlementSet` that intersected
properly, an `AuditEntry` that hashed over the right fields. All of it correct, none of it
durable. A gate that recomputes an entitlement from nothing on every request is a gate with
no grants in it, and a ledger that lives in a process ends when the process does.

**What breaks without this package.** Four modules' worth of leaves are blocked on somewhere
to put a row. A principal cannot be disabled, a channel identity cannot be bound, a grant
cannot be made or revoked, a field cannot be classified, and the audit trail - the one
artefact whose entire value is that it outlives whatever wrote it - does not survive a
restart.

**The direction of mirroring is one-way.** Every model here mirrors a type that already
exists in `brain.core`, `brain.gate` or `brain.audit`. The domain type is the definition;
the table is storage for it. Where the two could drift, the check constraint is generated
from the domain type's own constant - `one_of` in `identity.py` explains what that buys and
what it does not - so a change to an enum or a pattern shows up as a failing test rather
than as a row the database refuses at three in the morning.

`config.py` is the one module that mirrors nothing, and the exception is deliberate rather
than an omission. Configuration as data has no domain type above it because a setting is
whatever an operator needs to tune next; what it has instead is a declared value type and a
check constraint pinning the value to it, which is the same job done from the other end.

**Importing this package is what registers the tables.** `Base.metadata` is populated as a
side effect of the imports at the foot of this file, which is why they are here rather than
left to whoever needs a model. `migrations/env.py` imports this package for exactly that
reason, so `alembic revision --autogenerate` compares the database against the real
metadata - which only holds while the imports below stay exhaustive.

That is not a property anybody can be relied on to maintain by hand, and it has already
failed once: `routing.py` was added by a change that did not own this file, so for as long
as that lasted `import brain.tables` left three tables off the metadata and autogenerate
would have proposed dropping them. `tests/unit/test_tables.py` now imports this package in a
subprocess and compares what lands on the metadata against the tuple below, so a table
module that is never imported is a failing build rather than a quiet gap.

Task ids: M0.2.3, M1.1.5, M1.2.1, M1.2.2, M1.4.1, M1.4.3, M4.2.1, M24.1.1, M31.3.1.4
"""

from __future__ import annotations

# Imported for its side effect: `know.chunk` is declared in the module that reasons about
# how it is searched, so importing the package has to be what registers it. Without this
# line the table is absent from `Base.metadata` and autogenerate proposes dropping it.
from brain.knowledge import search as _search  # noqa: F401
from brain.tables.access_request import AccessRequestRow
from brain.tables.adoption import QuestionAskedRow
from brain.tables.agent import AgentRow
from brain.tables.agent_automation import AgentAutomationRow
from brain.tables.application_log import ApplicationLogRow
from brain.tables.artifact import ArtifactRow
from brain.tables.audit import AuditEntryRow
from brain.tables.automation import AutomationOwnerRow
from brain.tables.automation_run import AutomationRunRow, AutomationScheduleRow
from brain.tables.break_glass_notice import BreakGlassNoticeRow
from brain.tables.browsing import BrowserEnvelopeRow
from brain.tables.budget import BudgetVersionRow
from brain.tables.channel_event import ChannelEventRow
from brain.tables.chat import ConversationRow, MessageRole, MessageRow
from brain.tables.compliance import BreachCaseRow, SensitiveReferralRow
from brain.tables.config import SettingRow, SettingType
from brain.tables.connector_connection import ConnectorConnectionRow
from brain.tables.connector_sync import ConnectorSyncRow
from brain.tables.credential import CredentialWriteRow
from brain.tables.data_export import DataExportRow
from brain.tables.deployment_record import DeploymentRecordRow
from brain.tables.elevation import ElevationRequestRow
from brain.tables.erasure import ErasureOutcome, ErasureRequestRow
from brain.tables.fast_lane import FastPathRuleRow
from brain.tables.gate import (
    CapabilityGrantRow,
    CapabilityPackAssignmentRow,
    CapabilityPackRow,
    CapabilityRegistryRow,
    DepartmentRow,
    FieldPolicyRow,
    GrantsVersionRow,
    PolicyEpochRow,
    ScopeRow,
    TeamRow,
)
from brain.tables.group_role_rule import GroupRoleRuleRow
from brain.tables.identity import (
    DirectoryRoleGrantRow,
    PrincipalIdentityRow,
    PrincipalRow,
    SessionRow,
    one_of,
)
from brain.tables.knowledge import KnowledgeItemRow
from brain.tables.learning import CorrectionRow, LearningRow
from brain.tables.memory import AdaptiveMemoryRow, PersistentMemoryRow
from brain.tables.model_health import (
    ChainDepthAlertRow,
    ProviderHealthRow,
    ResidencyConstraintRow,
)
from brain.tables.model_registry import GoldenQuestionRow, ModelProviderRow, RoutingChangeRow
from brain.tables.operation import OperationRow
from brain.tables.organisation import DepartmentLeadRow, TeamMembershipRow
from brain.tables.outbox import OutboxDeliveryRow, OutboxEventRow, WebhookSubscriberRow
from brain.tables.plugin import PluginInstallRow, PluginVersionRow
from brain.tables.projection import ProjectedRecordRow
from brain.tables.question_gap import QuestionGapRow
from brain.tables.requirement_check import RequirementCheckRow
from brain.tables.resolution import (
    CanonicalEntityRow,
    EntityAliasRow,
    EntityIdentifierRow,
    EntityLinkRow,
)
from brain.tables.retention import LegalHoldRow, RetentionReleaseRow, RetentionReportRow
from brain.tables.review import ReviewDecisionRow
from brain.tables.role_grant import RoleGrantRow
from brain.tables.routing import ModelAttemptRow, RoutingRungRow, RoutingTierRow
from brain.tables.schedule import ControlRunRow
from brain.tables.sensitive_read import SensitiveReadRow
from brain.tables.service_account import ApiKeyRow, ServiceAccountRow
from brain.tables.skill import SkillAssignmentRow, SkillReviewRow, SkillRow
from brain.tables.spend import ReportRefreshRow, SpendActualRow
from brain.tables.staff import StaffMemberRow, StaffSyncRunRow
from brain.tables.suspension import SuspensionRow
from brain.tables.telemetry import RequestTelemetryRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tables.upgrade import UpgradeDeclineRow
from brain.tables.vault_access import VaultAccessRow
from brain.tables.webhook_change import WebhookChangeRow

#: Every table, in the order a migration must create them: a table appears after everything
#: it points at. The order is the migrations' own tuples end to end - 0002's seven, 0003's
#: nine, 0004's two, 0005's two, 0006's one, 0008's one, 0009's one, 0014's one - so
#: `tests/unit/test_tables.py` can compare this against their concatenation rather than
#: against a hand-maintained second copy. Each migration's downgrade reverses its own slice.
#: 0007 built no table: it widened two check constraints, which is why there is no slice for
#: it here, and neither did 0010 through 0013.
TABLES_IN_DEPENDENCY_ORDER: tuple[str, ...] = (
    # 0002_core_tables
    "auth.principal",
    "auth.principal_identity",
    "gate.capability_grant",
    "gate.capability_pack",
    "gate.capability_pack_assignment",
    "gate.field_policy",
    "obs.audit_entry",
    # 0003_resolver_and_tables
    "gate.scope",
    "gate.department",
    "gate.team",
    "auth.session",
    "gate.grants_version",
    "gate.policy_epoch",
    "ops.routing_tier",
    "ops.routing_rung",
    "ops.model_attempt",
    # 0004_capability_registry_and_config
    "gate.capability_registry",
    "ops.setting",
    # 0005_chat
    "chat.conversation",
    "chat.message",
    # 0006_directory_role_grant
    "auth.directory_role_grant",
    # 0008_projection
    "proj.record",
    # 0009_search. After the row plane and pointing at none of it: a chunk names its
    # document by id and the document plane owns no foreign key into the row plane.
    "know.chunk",
    # 0014_agent. References nothing, deliberately: the steward and the creator are plain
    # columns rather than foreign keys, so an agent outlives the account that built it.
    "agent.agent",
    # 0016_template. The instance follows the version it pins, which is the one foreign key
    # in this pair: an instance pinned to a manifest that does not exist is an agent nobody
    # can materialise. Neither points at `agent.agent`; see `brain.tables.template`.
    "agent.template_version",
    "agent.template_instance",
    # 0017_upgrade_decline. Last, because it points at both of 0016's: a decline belongs to
    # an install that exists and names a version that was published.
    "agent.upgrade_decline",
    # 0018_memory_stores. No foreign key into either, and that is deliberate rather than an
    # omission: a memory names the principal it was formed for, and a key into auth.principal
    # would mean deleting a person deletes the record of what the system learnt while acting
    # for them, which is the audit trail. The principal id is carried as a value.
    "mem.persistent",
    "mem.adaptive",
    # 0019_fast_path_rule. Points at nothing, deliberately: a rule names a source, an entity
    # and two projected fields as strings, and a foreign key into `proj.record` would make a
    # question shape depend on a record having been fetched, which is backwards. A rule for a
    # source nothing has projected yet is a rule that matches and answers nothing.
    "gate.fast_path_rule",
    # 0020_entity_resolution. `er.canonical` first, because the other three carry a foreign
    # key into it and it carries one into itself: `merged_into` is a self-reference, which is
    # what makes an issued id impossible to forward into nothing. None of the four keys into
    # `proj.record`, deliberately: a link is a statement about a source record and
    # `proj.record` is a bounded cache of one, so a key would make the resolution graph
    # depend on a cache having been filled. 0019 refuses the same key for the same reason.
    "er.canonical",
    "er.alias",
    "er.identifier",
    "er.link",
    # 0025_control_run. Points at nothing. The control it names lives in
    # `brain.ops.controls.CONTROLS`, which is a compiled constant rather than a table because
    # the set of mechanisms that must keep running is a fact about the product; a foreign key
    # would need a table mirroring that constant, and a mirror of a constant is the second
    # copy this repository refuses. The name is held to the registry by a check constraint
    # generated from it instead.
    "ops.control_run",
    # 0030_outbox. The delivery table last, because it points at the other two.
    "ops.webhook_subscriber",
    "ops.outbox_event",
    "ops.outbox_delivery",
    # 0031_budget. Points at nothing: a subject is a value, so a ceiling outlives its principal.
    "ops.budget_version",
    # 0032_plugin_registry. The version table first, because an install points at the version
    # it is running.
    "ops.plugin_version",
    "ops.plugin_install",
    # 0034_spend_ledger. Points at nothing: a principal, a department and an agent are values,
    # so a recorded cost outlives all three.
    "ops.spend_actual",
    # 0035_materialised_spend_report. Names a view, which is not a table and has no row here.
    "ops.report_refresh",
    # 0038_question_asked. Points at nothing: a principal and a department are values, so a
    # recorded question outlives both. Keyed on the trace, so a hop is not a second row.
    "ops.question_asked",
    # 0039_request_telemetry. Points at nothing, and partitioned by when the request arrived,
    # so its default partition is a table of the migration's and not of the metadata.
    "obs.request_telemetry",
    # 0040_knowledge_item. Points at nothing: a chunk names its document by id and this row is
    # that document, and no key runs between them while neither of their writers exists.
    "know.item",
    # 0041_browser_envelope. Points at nothing: the asker and the agent are values, so what a
    # run was permitted outlives both.
    "agent.browser_envelope",
    # 0042_suspension. Points at nothing: the principal and the agent are values, so what a
    # person was shown before something ran in somebody's name outlives both.
    "gate.suspension",
    # 0044_automation_owner. Points at nothing: the owner is a value, so what an automation
    # ran as outlives the person, and an automation whose owner has gone stays to be adopted.
    "gate.automation_owner",
    # 0049_retention_enforcement. The release last, because it names the report a person read
    # before releasing the sweep. A hold points at nothing: its subjects are values, so a hold
    # outlives the people it holds data about.
    "obs.legal_hold",
    "ops.retention_report",
    "ops.retention_release",
    # 0051_operation_ledger. Points at nothing: the principal is a value and the key is a digest
    # of the intent, so a record of an effect outlives everything it was about.
    "ops.operation",
    # 0052_review_decision. Last, because it points at both grant tables. A decision is never
    # retired, so the record of who reviewed a grant outlives the grant being removed.
    "gate.review_decision",
    # 0053_webhook_changes_and_data_exports. A change points at the subscriber it changed; an export
    # points at nothing, because the person who took it is a value and the record outlives them.
    "ops.webhook_change",
    "ops.data_export",
    # 0054_credential_and_retention_audit. Points at nothing: the writer is a value, and the setup
    # wizard writes a key before any principal exists to point at.
    "ops.credential_write",
    # 0055_agent_automation. Points at nothing: the agent and the principal are values, so the
    # record of what ran in a person's name outlives both.
    "agent.automation",
    # 0056_skill_library. A decision points at the skill it decides and an assignment at the
    # decision and the skill, so they follow it; the people are values.
    "agent.skill",
    "agent.skill_review",
    "agent.skill_assignment",
    # 0057_connector_connection. Points at nothing: both actors are values, so the record of who
    # let this system read a source outlives them.
    "ops.connector_connection",
    # 0058_artifact_store. Points at nothing: the agent, the run and the person are values, so the
    # record of what was produced outlives all three.
    "agent.artifact",
    # 0060_erasure_request. Points at nothing: the person and the administrator are values, so the
    # record that an erasure was asked for outlives the rows it erased.
    "ops.erasure_request",
    # 0061_learning_and_correction. Neither points at anything: a learning and a correction name
    # memories by id, and a memory id may be in either of 0018's tables, so a key into one would
    # refuse the other. The person who recorded a correction is a value, as every actor is.
    "mem.learning",
    "mem.correction",
    # 0062_organisation_and_elevation. A membership follows the team and the person it places, a
    # lead the department and the person, and a request the grant an approval wrote; the actors
    # are values, so who placed or approved somebody outlives them.
    "gate.team_membership",
    "gate.department_lead",
    "gate.elevation_request",
    # 0063_application_log. Points at nothing: a log row names a module, a trace reference and
    # an exception type as values, and names no person.
    "obs.application_log",
    # 0064_question_gap. Points at nothing: a department and a source are values, so a question the
    # install was not wired to answer is still counted after either is renamed.
    "ops.question_gap",
    # 0067_automation_run. Neither points at anything: the automation, its agent and the people
    # are values, so what ran in a person's name and why it stopped outlive all of them.
    "agent.automation_run",
    "agent.automation_schedule",
    # 0068_connector_sync. Points at nothing: the connection an attempt read with is named by its
    # id as a value, so a source connected again starts a history of its own.
    "ops.connector_sync",
    # 0091_deployment_record. Points at nothing: a deploy names an image and a commit as values,
    # and is kept apart from the permission ledger on purpose.
    "ops.deployment_record",
    # 0093_vault_leases_and_audit. Points at nothing: a slot is a value, so the record of who read
    # a key outlives the key.
    "ops.vault_access",
    # 0096_staff_roster. Point at nothing: a member is a digest and a run names its source as a
    # value, so neither hangs from a principal a later offboarding retires.
    "auth.staff_member",
    "auth.staff_sync_run",
    # 0095_service_accounts_and_partner_reach. An account points at its owning principal, and a
    # key at its account.
    "auth.service_account",
    "auth.api_key",
    # 0097_model_registry_and_matrix_gate. Only the change points at anything: the rung it edits.
    "ops.model_provider",
    "ops.golden_question",
    "ops.routing_change",
    # 0100_gate_front_half
    "gate.channel_event",
    # 0101_access_request. Points at nothing: the asker and the owner are values, so a request
    # outlives a change to either.
    "gate.access_request",
    # 0098_sensitive_reads_and_budget_audit. Points at nothing: the reader and the subject are
    # values, so the record of who read somebody's record outlives both.
    "ops.sensitive_read",
    # 0099_requirement_check. Points at nothing: a requirement is a register id and the person a
    # value, so the record of what was checked outlives both.
    "ops.requirement_check",
    # 0102_role_grant_and_team_grants
    "gate.role_grant",
    # 0104_compliance_record_and_decision_entries. Neither points at anything.
    "ops.breach_case",
    "ops.sensitive_referral",
    # 0109_group_role_rule
    "auth.group_role_rule",
    "gate.break_glass_notice",
    # 0108_provider_health_and_residency. Point at nothing: a deployment id is a string on a
    # rung, and an alert outlives the rung it names.
    "ops.provider_health",
    "ops.chain_depth_alert",
    "ops.residency_constraint",
)

__all__ = [
    "TABLES_IN_DEPENDENCY_ORDER",
    "AccessRequestRow",
    "AdaptiveMemoryRow",
    "AgentAutomationRow",
    "AgentRow",
    "ApiKeyRow",
    "ApplicationLogRow",
    "ArtifactRow",
    "AuditEntryRow",
    "AutomationOwnerRow",
    "AutomationRunRow",
    "AutomationScheduleRow",
    "BreachCaseRow",
    "BreakGlassNoticeRow",
    "BrowserEnvelopeRow",
    "BudgetVersionRow",
    "CanonicalEntityRow",
    "CapabilityGrantRow",
    "CapabilityPackAssignmentRow",
    "CapabilityPackRow",
    "CapabilityRegistryRow",
    "ChainDepthAlertRow",
    "ChannelEventRow",
    "ConnectorConnectionRow",
    "ConnectorSyncRow",
    "ControlRunRow",
    "ConversationRow",
    "CorrectionRow",
    "CredentialWriteRow",
    "DataExportRow",
    "DepartmentLeadRow",
    "DepartmentRow",
    "DeploymentRecordRow",
    "DirectoryRoleGrantRow",
    "ElevationRequestRow",
    "EntityAliasRow",
    "EntityIdentifierRow",
    "EntityLinkRow",
    "ErasureOutcome",
    "ErasureRequestRow",
    "FastPathRuleRow",
    "FieldPolicyRow",
    "GoldenQuestionRow",
    "GrantsVersionRow",
    "GroupRoleRuleRow",
    "KnowledgeItemRow",
    "LearningRow",
    "LegalHoldRow",
    "MessageRole",
    "MessageRow",
    "ModelAttemptRow",
    "ModelProviderRow",
    "OperationRow",
    "OutboxDeliveryRow",
    "OutboxEventRow",
    "PersistentMemoryRow",
    "PluginInstallRow",
    "PluginVersionRow",
    "PolicyEpochRow",
    "PrincipalIdentityRow",
    "PrincipalRow",
    "ProjectedRecordRow",
    "ProviderHealthRow",
    "QuestionAskedRow",
    "QuestionGapRow",
    "ReportRefreshRow",
    "RequestTelemetryRow",
    "RequirementCheckRow",
    "ResidencyConstraintRow",
    "RetentionReleaseRow",
    "RetentionReportRow",
    "ReviewDecisionRow",
    "RoleGrantRow",
    "RoutingChangeRow",
    "RoutingRungRow",
    "RoutingTierRow",
    "ScopeRow",
    "SensitiveReadRow",
    "SensitiveReferralRow",
    "ServiceAccountRow",
    "SessionRow",
    "SettingRow",
    "SettingType",
    "SkillAssignmentRow",
    "SkillReviewRow",
    "SkillRow",
    "SpendActualRow",
    "StaffMemberRow",
    "StaffSyncRunRow",
    "SuspensionRow",
    "TeamMembershipRow",
    "TeamRow",
    "TemplateInstanceRow",
    "TemplateVersionRow",
    "UpgradeDeclineRow",
    "VaultAccessRow",
    "WebhookChangeRow",
    "WebhookSubscriberRow",
    "one_of",
]
