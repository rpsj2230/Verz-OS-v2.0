"""Every door to the outside, and whether going through one twice does the thing twice.

`brain.ops.idempotency.issue_once` makes a side effect at most once per key, and a door is only
worth anything if nothing walks round it. So the question this module answers is the one that
makes M17.3.1's "every" a claim rather than a hope: **which calls in `src/brain` issue a side
effect, and is each of them inside the door?**

**The population is read off the code, and it is the protocols.** This repository puts every
client behind a `typing.Protocol`, and says why in CLAUDE.md: nothing that decides policy owns a
client, because a boundary cannot be tested through a module that opens a socket. So a new way to
reach the outside arrives as a protocol method, and `protocol_methods` finds every one by parsing
the source. `PORTS` classifies each by what repeating it does, and `classification_gaps` holds the
two in both directions: a method nobody classified is a finding, and so is a classification of a
method that no longer exists. A door cannot be added without somebody saying what walking through
it twice does. See `A_DOOR_NOBODY_CLASSIFIED_IS_A_SIDE_EFFECT_NOBODY_KEYED`.

**A call to a door that issues must be inside `issue_once`.** `unkeyed_effects` finds every call
to a method classified `Repeat.ISSUES` and accepts it in three shapes only: inside the effect
handed to `issue_once`, after `assert_no_side_effect` in the same function, or inside a method of
the same name, which is an implementation delegating to the port it implements and whose own
callers are checked instead. Anything else is a finding with a file and a line.

**The receiver is resolved where the code says what it is, and presumed to issue where it does
not.** Two ports share the name `send`: a channel's, which issues, and the outbox sender's, which
carries a key its receiver drops duplicates on. A call whose receiver is a parameter annotated with
a protocol classified as not issuing is resolved to that protocol; every other call to a method
name some issuing port declares is treated as issuing, because a concrete adapter's `send` is a
channel's `send`, and the mistake worth making is a finding somebody reads rather than a send
nobody keyed. See `A_RECEIVER_THIS_CANNOT_NAME_IS_PRESUMED_TO_ISSUE`.

**A callable over an agent's action is a door too.** `brain.gate.leash` runs an `Action` by
calling a function its caller hands in, so a parameter typed `Callable[[Action], ...]` that its
own function calls is found and classified in `CALLABLES` the way a protocol method is in
`PORTS`. `EFFECT_UNITS` names the types that mean "a side effect about to happen", and it holds
one. See `A_CALLABLE_OVER_A_SIDE_EFFECT_IS_A_DOOR_TOO`.

**What this does not see, stated.** A side effect issued by a concrete class that implements no
protocol and is called directly: an HTTP client constructed in a module and posted through. The
repository's rule is that this does not happen, and `brain.ops.independence` and the house style
hold part of it; this module holds the rest only as far as the rule is kept. A callable over a
side effect whose argument is not a type in `EFFECT_UNITS` is invisible, and so is a call through
a variable holding a bound method, or through `getattr`, for the reason `brain.ops.controls`
gives about its own call index.

Rejected: a decorator on each protocol method saying whether it issues. It puts the declaration
next to the door, which reads well, and it is ninety-odd edits across fifty modules, most of them
owned by work in flight, with the same completeness check needed afterwards to find the method that
was not decorated. The classification lives here, once, and the check reads the source both ways.

Task ids: M17.3.1
"""

from __future__ import annotations

import ast
import enum
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Final

#: The package this reads. A parameter everywhere below, so a test can point it at a tree of its
#: own and watch a finding be produced.
SRC: Final[Path] = Path(__file__).resolve().parents[1]

#: The door every issuing call must go through, and the refusal that is the other way past.
DOOR: Final = "issue_once"
NO_EFFECT_GUARD: Final = "assert_no_side_effect"

# ------------------------------------------------------------------ written-down reasons
#: Why every protocol method has to be classified, including the ones that plainly read.
A_DOOR_NOBODY_CLASSIFIED_IS_A_SIDE_EFFECT_NOBODY_KEYED: Final = (
    "A check that knew only the doors somebody listed as issuing would pass the day a new one "
    "arrived unlisted, which is the day it matters. So every protocol method is classified, the "
    "ones that read along with the ones that write, and a method with no classification fails. "
    "Classifying a read costs a line; an unclassified send costs a duplicate payment."
)

#: Why an unresolved receiver is treated as issuing.
A_RECEIVER_THIS_CANNOT_NAME_IS_PRESUMED_TO_ISSUE: Final = (
    "Source cannot always say what a receiver is: a concrete adapter's send is annotated with the "
    "adapter, not the protocol, and a self attribute has no annotation at the call. Resolving "
    "those as not issuing would let every concrete send through; resolving them as issuing makes "
    "the check ask for a key it may not need, which is a finding somebody reads and answers."
)


class Repeat(enum.StrEnum):
    """What calling a door a second time with the same arguments does."""

    #: A second effect somebody outside sees: a message read twice, a record written twice.
    ISSUES = "issues"
    #: Nothing changes anywhere.
    READS = "reads"
    #: A row in this system's own PostgreSQL, where a duplicate is a constraint's to refuse.
    WRITES_THIS_SYSTEMS_DATABASE = "writes_this_systems_database"
    #: The far end is left as the first call left it: a delete, a revoke, a put by content key.
    SAME_RESULT_WHEN_REPEATED = "same_result_when_repeated"
    #: Delivered at least once with a key the receiver drops duplicates on.
    KEYED_BY_THE_RECEIVER = "keyed_by_the_receiver"
    #: A second one exists until its own lifetime ends it, and nothing reads it after.
    EXPIRES_ON_ITS_OWN = "expires_on_its_own"
    #: A cache entry, a counter or a trace: rebuilt, recounted or read as an observation.
    DERIVED_STATE = "derived_state"
    #: Work done elsewhere that leaves nothing behind there: a model call, a parse, a sandbox.
    NO_EFFECT_AT_THE_FAR_END = "no_effect_at_the_far_end"
    #: A job on this system's queue, whose own effects go through doors classified here.
    ENQUEUES_WORK = "enqueues_work"


#: Why each classification is safe to repeat, or is not. Exhaustive over `Repeat`.
WHY: Final[Mapping[Repeat, str]] = MappingProxyType(
    {
        Repeat.ISSUES: (
            "a repeat is a second effect a person or a system outside reads, so every call is made "
            "through brain.ops.idempotency.issue_once under a derived key"
        ),
        Repeat.READS: "nothing changes anywhere, so a repeat is a second read",
        Repeat.WRITES_THIS_SYSTEMS_DATABASE: (
            "the row is in this system's own PostgreSQL, in a transaction the caller holds, and a "
            "duplicate is refused by the table's own key or merged by its own conflict clause"
        ),
        Repeat.SAME_RESULT_WHEN_REPEATED: (
            "the far end is left exactly as the first call left it: a second delete finds nothing, "
            "a second revoke finds it revoked, a second put writes the same bytes to the same key"
        ),
        Repeat.KEYED_BY_THE_RECEIVER: (
            "delivery is at least once by contract, brain.ops.outbox.DELIVERY_IS_AT_LEAST_ONCE, "
            "and the request carries a signed event id the receiver drops a duplicate on"
        ),
        Repeat.EXPIRES_ON_ITS_OWN: (
            "a second lease is a second credential that expires at its own time to live and is "
            "never read, because the borrower revokes and discards the one it was handed"
        ),
        Repeat.DERIVED_STATE: (
            "a cache entry is rebuilt from its source, a rate counter counts attempts and a trace "
            "is an observation read by its trace id, so a repeat changes no fact anybody acts on"
        ),
        Repeat.NO_EFFECT_AT_THE_FAR_END: (
            "the far end computes and forgets: a model answers, a parser parses, a sandbox with no "
            "network runs a script; the cost of a repeat is money and time, which budgets govern"
        ),
        Repeat.ENQUEUES_WORK: (
            "the job is a row on this system's own queue, and whatever it does outside goes "
            "through a door classified here, where a second run of the same job meets the same key"
        ),
    }
)


#: Every public method of every protocol under `src/brain`, by `module:Class.method`.
PORTS: Final[Mapping[str, Repeat]] = MappingProxyType(
    {
        # The automation gallery: an agent read, and installs in this system's own table, where a
        # second install is refused by the unique constraint and appends nothing.
        "brain.automation_gallery_routes:AgentRecords.agent": Repeat.READS,
        "brain.automation_gallery_routes:AutomationInstalls.installed_by": Repeat.READS,
        "brain.automation_gallery_routes:AutomationInstalls.install": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        # Starting and stopping an installed automation: a read of an agent's automations and a
        # write of its next run and the schedule row beside it, conditional on the next run shown,
        # so a second press finds the automation already moved and writes nothing.
        "brain.automation_schedule_routes:AutomationSchedules.listed": Repeat.READS,
        "brain.automation_schedule_routes:AutomationSchedules.change": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        # The skill library: reads, and inserts into this system's own tables, where a second
        # import or decision is refused by the key and appends nothing, and an assignment writes
        # only when the install is the one it was decided about.
        "brain.skill_routes:SkillLibrary.library": Repeat.READS,
        "brain.skill_routes:SkillLibrary.skill": Repeat.READS,
        "brain.skill_routes:SkillLibrary.add": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.skill_routes:SkillLibrary.decide": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.skill_routes:SkillLibrary.assign": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.skill_routes:AgentInstalls.agent": Repeat.READS,
        # Approvals: reads and writes of this system's own suspension rows.
        "brain.approval_routes:SuspensionSource.open_suspensions": Repeat.READS,
        "brain.approval_routes:SuspensionSource.suspension": Repeat.READS,
        "brain.approval_routes:HeldSuspensions.lock": Repeat.READS,
        "brain.approval_routes:HeldSuspensions.record": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.approval_routes:SuspensionStore.reading_as": Repeat.READS,
        "brain.approval_routes:SuspensionStore.holding": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.audit.record:LedgerWriter.append": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.automation_routes:RegistrationSource.registration": Repeat.READS,
        "brain.builder.drafts:DraftStore.add": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.builder.drafts:DraftStore.get": Repeat.READS,
        "brain.builder.drafts:DraftStore.append": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.builder.drafts:DraftStore.revisions": Repeat.READS,
        "brain.builder.drafts:DraftStore.record": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.builder.drafts:DraftStore.publications": Repeat.READS,
        # Audit, sessions and sign-in links (0050). A session's first sighting is this system's
        # own row with a conflict clause; ending and unlinking are guarded writes to its own
        # tables, where a second call finds the row already ended or already gone.
        "brain.audit_routes:LedgerWindows.window": Repeat.READS,
        "brain.audit.chain_check:LedgerSequence.after": Repeat.READS,
        "brain.audit.chain_check:LedgerSequence.at_seq": Repeat.READS,
        "brain.audit.chain_check:LedgerSequence.newest": Repeat.READS,
        # A requirement check (0099) is an append with no key: a second press is a second check,
        # which is what it is, since a later check supersedes and never edits an earlier one.
        "brain.requirement_check_routes:RequirementChecks.latest": Repeat.READS,
        "brain.requirement_check_routes:RequirementChecks.record": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.console.govern:LiveSession.is_live": Repeat.READS,
        "brain.identity.bearer:SessionLedger.standing": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.session_routes:SessionStore.open_sessions": Repeat.READS,
        "brain.session_routes:SessionStore.end": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.session_routes:SignInLinkStore.links": Repeat.READS,
        "brain.session_routes:SignInLinkStore.administrators_linked": Repeat.READS,
        "brain.session_routes:SignInLinkStore.unlink": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # The vault's key slots. A write puts the same key at the same path, so a repeat leaves
        # the slot as the first write left it apart from its version counter; reading the
        # version reads metadata only.
        "brain.ops.credentials:CredentialVault.static_kv_version": Repeat.READS,
        "brain.ops.credentials:CredentialVault.write_static_kv": Repeat.SAME_RESULT_WHEN_REPEATED,
        # The record of a kept key (0054): a row in this system's own table, whose trigger appends
        # the ledger entry. A repeat is a second row and a second entry, which is right, because a
        # repeated call follows a second write to the vault.
        "brain.ops.credentials:CredentialWrites.record": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # The browser sandbox. A runner's `act` is a click or a keystroke on somebody else's page
        # and is issued through `issue_once` inside the container, keyed on the instruction; the
        # rest of its browser reads. Every Engine call names a resource by the run it belongs to,
        # so a second create is refused as a conflict, a second start or join finds it done and a
        # second removal finds nothing. A killed proxy flow stays killed. A read-back is a read
        # through the gate, and a line to the control plane is a transcript entry.
        "brain.browsing.egress_addon:AnyFlow.kill": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.browsing.egress_addon:ProxiedFlow.kill": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.browsing.launcher:Engine.create_network": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.browsing.launcher:Engine.create_container": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.browsing.launcher:Engine.connect": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.browsing.launcher:Engine.start": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.browsing.launcher:Engine.remove_container": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.browsing.launcher:Engine.remove_network": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.browsing.launcher:Engine.labelled": Repeat.READS,
        "brain.browsing.launcher:Engine.runtimes": Repeat.READS,
        "brain.browsing.runner:Browser.navigate": Repeat.READS,
        "brain.browsing.runner:Browser.origin": Repeat.READS,
        "brain.browsing.runner:Browser.accessibility_tree": Repeat.READS,
        "brain.browsing.runner:Browser.act": Repeat.ISSUES,
        "brain.browsing.runner:Browser.capture": Repeat.READS,
        "brain.browsing.runner:Channel.receive": Repeat.READS,
        "brain.browsing.runner:Channel.emit": Repeat.DERIVED_STATE,
        "brain.browsing.verification:ReadBackPort.look": Repeat.READS,
        # The cache.
        "brain.cache:ValkeyClient.get": Repeat.READS,
        "brain.cache:ValkeyClient.setex": Repeat.DERIVED_STATE,
        "brain.cache:ValkeyClient.ping": Repeat.READS,
        "brain.cache:AsyncValkeyClient.get": Repeat.READS,
        "brain.cache:AsyncValkeyClient.setex": Repeat.DERIVED_STATE,
        "brain.cache:AsyncValkeyClient.ping": Repeat.READS,
        "brain.cache:OwnedAsyncValkeyClient.aclose": Repeat.NO_EFFECT_AT_THE_FAR_END,
        # Channels. `send` is a message a person reads.
        "brain.channels.adapter:ChannelAdapter.capabilities": Repeat.READS,
        "brain.channels.adapter:ChannelAdapter.normalise": Repeat.READS,
        "brain.channels.adapter:ChannelAdapter.send": Repeat.ISSUES,
        "brain.channels.adapter:ChannelAdapter.healthy": Repeat.READS,
        "brain.channels.binding:NonceLedger.consume": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # Connectors: every reader reads, and no connector declares a write.
        "brain.connectors.freshdesk:PageReader.read": Repeat.READS,
        "brain.connectors.google_drive:PageReader.read": Repeat.READS,
        "brain.connectors.laravel:ViewReader.rows": Repeat.READS,
        "brain.connectors.lark_base:RecordReader.read": Repeat.READS,
        "brain.connectors.lark_wiki:WikiReader.list_nodes": Repeat.READS,
        "brain.connectors.lark_wiki:WikiReader.read_node": Repeat.READS,
        # A staff directory is searched read-only and unbound; unbinding twice leaves it unbound.
        "brain.connectors.ldap_directory:DirectoryConnection.search_page": Repeat.READS,
        "brain.connectors.ldap_directory:DirectoryConnection.close": (
            Repeat.SAME_RESULT_WHEN_REPEATED
        ),
        "brain.deployment.database:Executor.execute": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # The gate.
        "brain.gate.answer_cache:AnswerStore.get": Repeat.READS,
        "brain.gate.answer_cache:AnswerStore.set": Repeat.DERIVED_STATE,
        "brain.gate.compose:TraceSink.emit": Repeat.DERIVED_STATE,
        "brain.gate.finish:RequestRecorder.finished": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # The answer lane's model step: passages found at a reach, and a model that answers and
        # forgets, whose attempt rows are written through `AttemptLog`'s own doors.
        "brain.gate.model_lane:PassageSearch.passages": Repeat.READS,
        "brain.gate.model_lane:AnswerModel.complete": Repeat.NO_EFFECT_AT_THE_FAR_END,
        "brain.gate.provenance:Cited.render": Repeat.READS,
        "brain.gate.resolve:VersionSource.grants_version": Repeat.READS,
        "brain.gate.resolve:EntitlementStore.load": Repeat.READS,
        "brain.gate.resolve:EntitlementCache.get": Repeat.READS,
        "brain.gate.resolve:EntitlementCache.set": Repeat.DERIVED_STATE,
        # Identity.
        "brain.identity.bearer:KeySource.keys_for": Repeat.READS,
        "brain.identity.bearer:KeySource.key_for": Repeat.READS,
        "brain.identity.oidc:PrincipalDirectory.principal_for_subject": Repeat.READS,
        "brain.identity.staff_source:StaffSource.roster": Repeat.READS,
        # Knowledge: parsing, embedding and reading rows.
        "brain.knowledge.embed_queue:EmbeddingService.embed": Repeat.NO_EFFECT_AT_THE_FAR_END,
        "brain.knowledge.parse_layout:LayoutService.layout": Repeat.NO_EFFECT_AT_THE_FAR_END,
        "brain.knowledge.parse_ocr:OcrEngine.read": Repeat.NO_EFFECT_AT_THE_FAR_END,
        "brain.knowledge.rows:RowSource.rows": Repeat.READS,
        "brain.knowledge.scanning:Scanner.scan": Repeat.NO_EFFECT_AT_THE_FAR_END,
        # Connect Lark's settings: installation rows upserted on their live key, so a second save
        # writes the same values over the first.
        "brain.lark_connect_routes:LarkSettings.save": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.knowledge.scanning:Parser.parse": Repeat.NO_EFFECT_AT_THE_FAR_END,
        "brain.member.connections:TokenRevoker.revoke": Repeat.SAME_RESULT_WHEN_REPEATED,
        # The model executor: the ladder is read on every call, and each attempt is one row in
        # `ops.model_attempt`, inserted under the trace's unique sequence and finished by its id.
        "brain.models.calls:Ladder.current": Repeat.READS,
        "brain.models.calls:AttemptLog.started": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.models.calls:AttemptLog.finished": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # Providers added from the console: a driver per row, built once and kept, and which of
        # their keys this process's environment holds.
        "brain.models.calls:AddedProviders.drivers": Repeat.DERIVED_STATE,
        "brain.models.calls:AddedProviders.held": Repeat.READS,
        # Provider health (M5.4.3, M5.4.8): a live outcome appended to its deployment's ring in
        # `ops.provider_health`, and a depth alert appended to `ops.chain_depth_alert`. Both are
        # rows here; a second append is a second observation, read as one.
        "brain.models.calls:HealthLog.observed": Repeat.DERIVED_STATE,
        "brain.models.calls:DepthAlerts.raised": Repeat.DERIVED_STATE,
        # The prober (M5.4.7): a claim is a conditional upsert that returns nothing when repeated
        # inside the interval, a probe is one model call that leaves nothing at the provider, its
        # outcome is a ring entry, and the keys are read from the vault or the environment.
        "brain.ops.model_probe_run:ProbeStore.claim": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.model_probe_run:ProbeStore.observed": Repeat.DERIVED_STATE,
        "brain.ops.model_probe_run:ProbeSender.send": Repeat.NO_EFFECT_AT_THE_FAR_END,
        "brain.ops.model_probe_run:ProviderKeys.held": Repeat.READS,
        "brain.ops.model_probe_run:ProviderKeys.lookup": Repeat.READS,
        # The matrix gate asks the golden questions through the lane: model calls that leave
        # nothing at the provider, and attempt rows under a trace of their own per question.
        "brain.ops.matrix_gate_run:MatrixGate.decide": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # The default ladder: rows in `ops.routing_rung`, written under a lock and refused by the
        # table's unique live position when the ladder is already held.
        "brain.models.default_ladder:LadderWriter.write": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.models.driver:ModelDriver.complete": Repeat.NO_EFFECT_AT_THE_FAR_END,
        # Operations.
        "brain.ops.automation_owner:PrincipalRecords.live_principal": Repeat.READS,
        # A tool call runs whatever the tool does, and a tool may declare a write.
        "brain.ops.automation_piece:ToolCaller.call": Repeat.ISSUES,
        "brain.ops.digest_delivery:DigestSender.send": Repeat.ISSUES,
        # The Import and export screen's export: a read of the ledger and one insert into this
        # system's own table, whose trigger appends to the ledger, in one transaction.
        "brain.ops.data_export_store:ExportRecords.take_audit_export": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.ops.data_export_store:ExportRecords.taken_by": Repeat.READS,
        # The Retention screen's export log: a read of the same table, every person's rows.
        "brain.ops.data_export_store:ExportLog.recent": Repeat.READS,
        # The Retention screen's erasure queue: one insert into this system's own table, whose
        # trigger appends to the ledger, and whose open-request key refuses a second one.
        "brain.ops.deployment_store:Connection.execute": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.erasure_store:ErasureRecords.file": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.erasure_store:ErasureRecords.requests": Repeat.READS,
        # A process's own vault token: its standing is a read, and a second renewal inside the
        # period sets the token to the same full period the first did.
        "brain.ops.vault_renewal:SelfRenewing.token_standing": Repeat.READS,
        "brain.readiness:TokenLookup.token_standing": Repeat.READS,
        "brain.ops.vault_renewal:SelfRenewing.renew_self": Repeat.SAME_RESULT_WHEN_REPEATED,
        # The Secrets vault screen and the provider key refresh: the seal, a slot's metadata and a
        # slot's fields are reads, and so is the count of what the audit shipper wrote.
        "brain.ops.credentials:CredentialVault.read_static_kv": Repeat.READS,
        "brain.ops.provider_keys:StaticKvReader.read_static_kv": Repeat.READS,
        "brain.ops.vault_status:TokenLookup.token_standing": Repeat.READS,
        "brain.ops.vault_status:VaultStatusReader.seal_status": Repeat.READS,
        "brain.ops.vault_status:VaultStatusReader.static_kv_defined": Repeat.READS,
        "brain.ops.vault_status:VaultStatusReader.static_kv_version": Repeat.READS,
        "brain.ops.vault_audit_ship:VaultAccessRecords.since": Repeat.READS,
        # The Webhooks screen. Each write is this system's own rows in one transaction; the vault
        # write inside a registration or a rotation goes through `CredentialVault.write_static_kv`,
        # classified above as the same result when repeated.
        "brain.ops.webhook_store:WebhookRecords.registered": Repeat.READS,
        "brain.ops.webhook_store:WebhookRecords.register": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.webhook_store:WebhookRecords.replace_secret": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.ops.webhook_store:WebhookRecords.switch_off": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.webhook_store:WebhookRecords.dispatcher": Repeat.READS,
        # The Connectors screen. A connection is this system's own row in one transaction, with the
        # key written inside it through `CredentialVault.write_static_kv`, classified above; a
        # repeat finds the source already connected and is refused before its key is written. A
        # disconnect is one update, and a repeat finds nothing live to mark.
        "brain.ops.connector_store:ConnectorRecords.connected": Repeat.READS,
        "brain.ops.connector_store:ConnectorRecords.connect": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.connector_store:ConnectorRecords.disconnect": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        # The Learning screen's undo and a memory's edit. Each is this system's own rows in one
        # transaction, decided under a lock on the memory; a repeat reads the first one's correction
        # and writes nothing, which is `brain.memory.digest.undo`'s own idempotency.
        "brain.ops.memory_store:MemoryRecords.undo": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.memory_store:MemoryRecords.edit": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # The Departments and teams screen. Each is this system's own row in one transaction: a
        # repeated placement or appointment meets the partial unique index and is refused, and a
        # repeated ending finds nothing live to end.
        "brain.identity.organisation_store:OrganisationRecords.place": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:OrganisationRecords.unplace": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:OrganisationRecords.appoint": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:OrganisationRecords.stand_down": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        # The same screen's structure. Each is this system's own rows in one transaction: a repeated
        # creation meets the live name and is refused, a repeated rename or retirement no longer
        # finds the name it expects or a live row, and nothing is written twice.
        "brain.identity.organisation_store:StructureRecords.found_department": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:StructureRecords.rename_department": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:StructureRecords.retire_department": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:StructureRecords.add_team": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:StructureRecords.rename_team": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:StructureRecords.retire_team": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:StructureRecords.draw_scope": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.identity.organisation_store:StructureRecords.retire_scope": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        # The Roles screen. An appointment is one row in one transaction and a repeat meets the
        # standing grant's partial unique index; a removal retires a live row and a repeat finds
        # none. The two reads write nothing.
        "brain.identity.role_store:RoleRecords.holders": Repeat.READS,
        "brain.identity.role_store:RoleRecords.one": Repeat.READS,
        "brain.identity.role_store:RoleRecords.appoint": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.identity.role_store:RoleRecords.retire": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # The group mapping on the Roles screen, and the sync at sign-in. A rule is one row and a
        # repeat meets the one-live-rule-per-group index; a retirement finds no live row the
        # second time; a sync reconciles to the token, so a repeat changes nothing.
        "brain.identity.group_sync:GroupRuleRecords.rules": Repeat.READS,
        "brain.identity.group_sync:GroupRuleRecords.synced": Repeat.READS,
        "brain.identity.group_sync:GroupRuleRecords.one": Repeat.READS,
        "brain.identity.group_sync:GroupRuleRecords.add": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.identity.group_sync:GroupRuleRecords.retire": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.identity.group_sync:Applies.apply": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.identity.bearer:MembershipObserver.observe": Repeat.SAME_RESULT_WHEN_REPEATED,
        # The Elevation requests screen. A request is a row, and a repeat is a second request the
        # screen lists; a decision is one transaction on a pending row, and a repeat finds it
        # decided.
        "brain.gate.elevation_store:ElevationRecords.requests": Repeat.READS,
        "brain.gate.elevation_store:ElevationRecords.file": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.gate.elevation_store:ElevationRecords.approve": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.gate.elevation_store:ElevationRecords.deny": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        # The break-glass notices a Super Admin reads on the Elevation screen: a read.
        "brain.gate.elevation_store:NoticeRecords.addressed_to": Repeat.READS,
        "brain.ops.erasure:Hold.is_active": Repeat.READS,
        "brain.ops.erasure:StoreEraser.count_for": Repeat.READS,
        "brain.ops.erasure:StoreEraser.erase": Repeat.SAME_RESULT_WHEN_REPEATED,
        # The ledger keys everything else and is keyed by its own primary key.
        "brain.ops.idempotency:OperationLedger.claim": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.idempotency:OperationLedger.win": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.idempotency:OperationLedger.settle": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.inference_client:InferenceResponse.json": Repeat.READS,
        "brain.ops.inference_client:InferenceTransport.post": Repeat.NO_EFFECT_AT_THE_FAR_END,
        "brain.ops.limit_store:WindowPipeline.watch": Repeat.DERIVED_STATE,
        "brain.ops.limit_store:WindowPipeline.multi": Repeat.DERIVED_STATE,
        "brain.ops.limit_store:WindowPipeline.execute": Repeat.DERIVED_STATE,
        "brain.ops.limit_store:WindowPipeline.zrange": Repeat.READS,
        "brain.ops.limit_store:WindowPipeline.zremrangebyscore": Repeat.DERIVED_STATE,
        "brain.ops.limit_store:WindowPipeline.zadd": Repeat.DERIVED_STATE,
        "brain.ops.limit_store:WindowPipeline.expire": Repeat.DERIVED_STATE,
        "brain.ops.limit_store:WindowClient.pipeline": Repeat.READS,
        "brain.ops.object_store:StaticKvReader.read_static_kv": Repeat.READS,
        # Reading a connected source on a schedule. A reading computes a page's arguments and a
        # row's record from what it is handed, the key is read from the vault, a call is a GET to
        # a source this connection may only read, and the screen reads the attempts; none changes
        # anything anywhere, so a repeat is a second read. The writes a run makes go through
        # `brain.ops.connector_sync_store`'s statements in this system's own database.
        "brain.ops.connector_sync:SourceReading.entities": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.refresh_interval": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.operation": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.first_page": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.next_page": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.call_headers": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.interpret": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.retry_after": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.allowance_spent": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.projected": Repeat.READS,
        "brain.ops.connector_sync:SourceReading.document": Repeat.READS,
        # A run's vault lease (0093): a child token minted per attempt that expires at its own
        # TTL, read through once and revoked at the attempt's end, where a second revoke finds it
        # gone. See `brain.ops.connector_lease`.
        "brain.ops.connector_sync_run:ConnectorKeys.lease": Repeat.EXPIRES_ON_ITS_OWN,
        "brain.ops.connector_sync_run:KeyLease.key": Repeat.READS,
        "brain.ops.connector_sync_run:KeyLease.close": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.ops.connector_sync_run:RunTokenVault.mint_role_token": Repeat.EXPIRES_ON_ITS_OWN,
        "brain.ops.connector_sync_run:RunTokenVault.holding": Repeat.READS,
        "brain.ops.connector_sync_run:RunKeyReader.read_static_kv": Repeat.READS,
        "brain.ops.connector_sync_run:RunKeyReader.revoke_self": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.ops.connector_sync_store:LeaseCounts.tallies": Repeat.READS,
        "brain.ops.connector_sync_run:SourceCaller.get": Repeat.READS,
        "brain.ops.connector_sync_store:ConnectorSyncRecords.states": Repeat.READS,
        # A delivery is a request somebody else's server acts on, so every one is made inside
        # `issue_once` under a key per attempt, and the receiver's duty to drop a repeated event
        # id covers the one repeat the ledger cannot: a request that left and was never answered.
        "brain.ops.outbox_store:Sender.send": Repeat.ISSUES,
        "brain.ops.outbox_store:SigningKeys.signing_secret": Repeat.READS,
        # Email. A message to a relay is read by a person, so every one is made inside
        # `issue_once`; see `brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION`.
        "brain.ops.mail:MailTransport.send": Repeat.ISSUES,
        "brain.ops.queue:QueueDriver.enqueue": Repeat.ENQUEUES_WORK,
        "brain.ops.queue:QueueDriver.fetch": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.queue:QueueDriver.complete": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.queue:QueueDriver.fail": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.retention:StoreSweeper.census": Repeat.READS,
        "brain.ops.retention:StoreSweeper.expire": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.ops.secrets:Vault.issue": Repeat.EXPIRES_ON_ITS_OWN,
        "brain.ops.secrets:Vault.revoke": Repeat.SAME_RESULT_WHEN_REPEATED,
        # A handover: reads of this install's own database and objects, and removals that leave
        # the far end as the first call left it. A schema already dropped is checked, not dropped.
        "brain.ops.handover_run:Database.tables": Repeat.READS,
        "brain.ops.handover_run:Database.copy_csv": Repeat.READS,
        "brain.ops.handover_run:Database.live_connectors": Repeat.READS,
        "brain.ops.handover_run:Database.schema_exists": Repeat.READS,
        "brain.ops.handover_run:Database.drop_schema": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.ops.handover_run:Objects.get_object": Repeat.READS,
        "brain.ops.handover_run:Objects.delete_object": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.ops.handover_run:Objects.list_objects": Repeat.READS,
        "brain.ops.handover_run:InstallDatabase.saved_settings": Repeat.READS,
        "brain.ops.handover_run:InstallDatabase.close": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.ops.storage:StorageBackend.put_object": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.ops.storage:StorageBackend.get_object": Repeat.READS,
        "brain.ops.storage:StorageBackend.delete_object": Repeat.SAME_RESULT_WHEN_REPEATED,
        "brain.ops.storage:StorageBackend.list_objects": Repeat.READS,
        "brain.ops.storage:BucketCounter.usage": Repeat.READS,
        "brain.seed:Executor.execute": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.setup_routes:Appointer.administrators": Repeat.READS,
        "brain.setup_routes:Appointer.appoint": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.sign_in_routes:SignInWriter.sign_ins": Repeat.READS,
        "brain.sign_in_routes:SignInWriter.bind": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.tools.fetch:Resolver.resolve": Repeat.READS,
        "brain.tools.fetch:Fetcher.get_once": Repeat.READS,
        "brain.tools.run_skill:ScriptRunner.run": Repeat.NO_EFFECT_AT_THE_FAR_END,
        "brain.tools.run_skill:SkillLibrary.pinned_skill": Repeat.READS,
        # Service accounts and disabling a person (0095). Registering refuses a taken id, a third
        # live key is refused under the account's lock, and a retirement or a disable that finds
        # the row already in that state writes nothing, so a second call adds no second act.
        "brain.identity.bearer:ServiceAccountDirectory.service_account_for_subject": Repeat.READS,
        "brain.identity.bearer:ServiceAccountDirectory.service_account_for_key": Repeat.READS,
        "brain.identity.bearer:ServiceAccountDirectory.live_owner": Repeat.READS,
        "brain.service_account_routes:ServiceAccountStore.owned": Repeat.READS,
        "brain.service_account_routes:ServiceAccountStore.register": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.service_account_routes:ServiceAccountStore.issue_key": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.service_account_routes:ServiceAccountStore.revoke_key": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.service_account_routes:ServiceAccountStore.retire": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.principal_state_routes:PrincipalStateStore.set_disabled": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        # The compliance stores (`0104`): a referral, a named person, a breach case, a denial.
        "brain.ops.breach_store:BreachCases.open": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.breach_store:BreachCases.cases": Repeat.READS,
        "brain.ops.breach_store:BreachCases.move": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.denial_store:Denials.denied": Repeat.WRITES_THIS_SYSTEMS_DATABASE,
        "brain.ops.read_counts_store:ReadCountSource.counts": Repeat.READS,
        "brain.ops.sensitive_referral_store:SensitiveReferrals.refer": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.ops.sensitive_referral_store:SensitiveReferrals.named": Repeat.READS,
        "brain.ops.sensitive_referral_store:SensitiveReferrals.name": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.ops.sensitive_referral_store:SensitiveReferrals.mine": Repeat.READS,
        "brain.ops.sensitive_referral_store:SensitiveReferrals.handle": (
            Repeat.WRITES_THIS_SYSTEMS_DATABASE
        ),
        "brain.ops.sensitive_referral_store:SensitiveReferrals.tally": Repeat.READS,
    }
)

#: Why a parameter typed as a callable over an action is a door as well as a protocol method is.
A_CALLABLE_OVER_A_SIDE_EFFECT_IS_A_DOOR_TOO: Final = (
    "brain.gate.leash.Action is one side effect an agent is about to have, and the leash runs it "
    "by calling a function its caller hands in rather than a method on a protocol. A scan that "
    "only read protocols would never see the one door the whole task lane exists to govern. So a "
    "parameter typed Callable[[Action], ...] that its own function calls is found and classified "
    "like a protocol method, and a call to one classified as issuing is held to the same door."
)

#: The types whose instances are a side effect about to happen, by `module:Class`.
EFFECT_UNITS: Final[frozenset[str]] = frozenset({"brain.gate.leash:Action"})

#: Every called parameter typed as a callable over an effect unit, by `module:function.param`.
CALLABLES: Final[Mapping[str, Repeat]] = MappingProxyType(
    {
        # A shadow run renders what would have happened and does nothing.
        "brain.gate.leash:run_shadow.simulate": Repeat.NO_EFFECT_AT_THE_FAR_END,
        # The real run. The one door in the task lane, called inside the effect `run_real`
        # hands `issue_once`. What a repeat is handed is decided in `brain.gate.leash`:
        # `AN_ACTION_THAT_ALREADY_RAN_IS_REPORTED_AND_NOT_RUN_AGAIN`.
        "brain.gate.leash:run_real.execute": Repeat.ISSUES,
    }
)


# ------------------------------------------------------------------------ reading the code
def _module_name(path: Path, src: Path) -> str:
    parts = path.relative_to(src).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join((src.name, *parts))


@cache
def _parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _sources(src: Path) -> Iterator[tuple[str, ast.Module]]:
    for path in sorted(src.rglob("*.py")):
        yield _module_name(path, src), _parsed(path)


def _is_protocol(node: ast.ClassDef) -> bool:
    for base in node.bases:
        target = base.value if isinstance(base, ast.Subscript) else base
        if isinstance(target, ast.Name) and target.id == "Protocol":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "Protocol":
            return True
    return False


def _is_property(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(one, ast.Name) and one.id == "property" for one in node.decorator_list)


def protocol_methods(src: Path = SRC) -> tuple[str, ...]:
    """Every public, non-property method of every top-level protocol, as `module:Class.method`.

    A property is an attribute read and not a door, so it is left out; a name with a leading
    underscore is not part of what a protocol asks of its implementations.
    """
    found: list[str] = []
    for module, tree in _sources(src):
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not _is_protocol(node):
                continue
            for item in node.body:
                if (
                    isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
                    and not item.name.startswith("_")
                    and not _is_property(item)
                ):
                    found.append(f"{module}:{node.name}.{item.name}")
    return tuple(found)


def _unit_names(module: str, tree: ast.Module, units: frozenset[str]) -> frozenset[str]:
    """The local names this module uses for a type in `units`: imported, or declared here."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.update(
                alias.asname or alias.name
                for alias in node.names
                if f"{node.module}:{alias.name}" in units
            )
        elif isinstance(node, ast.ClassDef) and f"{module}:{node.name}" in units:
            names.add(node.name)
    return frozenset(names)


def _takes_a_unit(annotation: ast.expr | None, names: frozenset[str]) -> bool:
    """Whether an annotation is `X[[..., Unit, ...], ...]` for one of these names.

    Any subscript whose first parameter is a list of argument types, rather than `Callable` by
    name: a mutation showed a check of the name admitted nothing else in this tree, since only a
    callable is written with an argument list, and a generic of its own taking one is a callable
    by another name, which is the thing this looks for.
    """
    if not isinstance(annotation, ast.Subscript):
        return False
    parts = annotation.slice
    if not isinstance(parts, ast.Tuple) or not parts.elts:
        return False
    accepted = parts.elts[0]
    return isinstance(accepted, ast.List) and any(
        isinstance(one, ast.Name) and one.id in names for one in accepted.elts
    )


def _called_unit_callables(
    module: str, tree: ast.Module, units: frozenset[str]
) -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef, str]]:
    """Each parameter typed as a callable over an effect unit that its own function calls."""
    names = _unit_names(module, tree, units)
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        arguments = function.args
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
            if not _takes_a_unit(argument.annotation, names):
                continue
            called = any(
                isinstance(one, ast.Call)
                and isinstance(one.func, ast.Name)
                and one.func.id == argument.arg
                for one in ast.walk(function)
            )
            if called:
                yield f"{module}:{function.name}.{argument.arg}", function, argument.arg


def effect_callables(src: Path = SRC, units: frozenset[str] = EFFECT_UNITS) -> tuple[str, ...]:
    """Every parameter typed as a callable over an effect unit that is called, as
    `module:function.parameter`. See `A_CALLABLE_OVER_A_SIDE_EFFECT_IS_A_DOOR_TOO`.
    """
    return tuple(
        name
        for module, tree in _sources(src)
        for name, _, _ in _called_unit_callables(module, tree, units)
    )


def classification_gaps(
    ports: Mapping[str, Repeat] = PORTS,
    src: Path = SRC,
    callables: Mapping[str, Repeat] = CALLABLES,
    units: frozenset[str] = EFFECT_UNITS,
) -> tuple[str, ...]:
    """Every door nobody classified, and every classification of nothing.

    Both kinds of door: a protocol method, and a called parameter typed as a callable over an
    effect unit. See `A_DOOR_NOBODY_CLASSIFIED_IS_A_SIDE_EFFECT_NOBODY_KEYED`.
    """
    findings: list[str] = []
    for declared, classified, kind in (
        (set(protocol_methods(src)), set(ports), "a protocol method"),
        (set(effect_callables(src, units)), set(callables), "a callable over a side effect"),
    ):
        findings.extend(
            f"{name}: {kind} with no classification, so nothing says whether calling it twice "
            "does something twice"
            for name in sorted(declared - classified)
        )
        findings.extend(
            f"{name}: classified here and declared nowhere, so the classification describes a "
            "door that is gone"
            for name in sorted(classified - declared)
        )
    return tuple(findings)


class Admitted(enum.StrEnum):
    """How one call to a door that issues is admitted, or that it is not."""

    #: Inside the effect handed to `issue_once`.
    THROUGH_THE_DOOR = "through_the_door"
    #: After `assert_no_side_effect` in the same function.
    NOTHING_TO_KEY = "nothing_to_key"
    #: Inside a method of the same name: an implementation delegating to its port.
    DELEGATES = "delegates"
    #: None of those.
    UNKEYED = "unkeyed"


@dataclass(frozen=True)
class EffectCall:
    """One call to a door that issues, and how it was admitted."""

    module: str
    function: str
    line: int
    method: str
    admitted: Admitted

    def sentence(self) -> str:
        return (
            f"{self.module}:{self.function} line {self.line} calls .{self.method}, which issues a "
            f"side effect, outside {DOOR} and with no {NO_EFFECT_GUARD} before it"
        )


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _enclosing(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> Iterator[ast.AST]:
    current = parents.get(node)
    while current is not None:
        yield current
        current = parents.get(current)


def _holder(
    node: ast.AST, parents: Mapping[ast.AST, ast.AST], tree: ast.Module
) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.Module:
    """The nearest function or module whose body a name used at `node` would be defined in."""
    for one in _enclosing(node, parents):
        if isinstance(one, ast.FunctionDef | ast.AsyncFunctionDef | ast.Module):
            return one
    return tree


def _keyed_scopes(tree: ast.Module, parents: Mapping[ast.AST, ast.AST]) -> set[ast.AST]:
    """Every function or lambda handed to `issue_once` as its effect, in this module."""
    keyed: set[ast.AST] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) != DOOR:
            continue
        effect: ast.expr | None = next(
            (one.value for one in node.keywords if one.arg == "effect"), None
        )
        if effect is None and len(node.args) >= 3:
            effect = node.args[2]
        if isinstance(effect, ast.Lambda):
            keyed.add(effect)
        elif isinstance(effect, ast.Name):
            holder = _holder(node, parents, tree)
            keyed.update(
                one
                for one in holder.body
                if isinstance(one, ast.FunctionDef | ast.AsyncFunctionDef) and one.name == effect.id
            )
    return keyed


def _annotation_name(annotation: ast.expr | None) -> str:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value.rsplit(".", 1)[-1]
    return ""


def _receiver_class(call: ast.Call, function: ast.FunctionDef | ast.AsyncFunctionDef | None) -> str:
    """The annotated class of the call's receiver, where a parameter of the function names it."""
    func = call.func
    if function is None or not isinstance(func, ast.Attribute):
        return ""
    receiver = func.value
    if not isinstance(receiver, ast.Name):
        return ""
    arguments = function.args
    for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
        if argument.arg == receiver.id:
            return _annotation_name(argument.annotation)
    return ""


def effect_calls(
    ports: Mapping[str, Repeat] = PORTS,
    src: Path = SRC,
    callables: Mapping[str, Repeat] = CALLABLES,
    units: frozenset[str] = EFFECT_UNITS,
) -> tuple[EffectCall, ...]:
    """Every call to a door that issues, and how each is admitted. See the module docstring.

    In module order and then line order, so two runs over an unchanged tree print the same list.
    A call resolved to a port that does not issue is not a call to a door that issues and is not
    listed at all.
    """
    issuing: dict[str, set[str]] = {}
    other: dict[str, set[str]] = {}
    for name, repeat in ports.items():
        owner, _, method = name.partition(":")[2].partition(".")
        (issuing if repeat is Repeat.ISSUES else other).setdefault(method, set()).add(owner)

    found: list[EffectCall] = []
    for module, tree in _sources(src):
        parents = _parents(tree)
        keyed = _keyed_scopes(tree, parents)
        for name, declaring, parameter in _called_unit_callables(module, tree, units):
            if callables.get(name) is not Repeat.ISSUES:
                continue
            for node in ast.walk(declaring):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == parameter
                ):
                    continue
                found.append(
                    EffectCall(
                        module=module,
                        function=declaring.name,
                        line=node.lineno,
                        method=parameter,
                        admitted=_admitted(
                            node, list(_enclosing(node, parents)), declaring, keyed, parents
                        ),
                    )
                )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            method = node.func.attr
            if method not in issuing:
                continue
            chain = list(_enclosing(node, parents))
            function = next(
                (one for one in chain if isinstance(one, ast.FunctionDef | ast.AsyncFunctionDef)),
                None,
            )
            receiver = _receiver_class(node, function)
            if receiver in other.get(method, set()) and receiver not in issuing[method]:
                continue
            found.append(
                EffectCall(
                    module=module,
                    function="<module>" if function is None else function.name,
                    line=node.lineno,
                    method=method,
                    admitted=_admitted(node, chain, function, keyed, parents),
                )
            )
    return tuple(sorted(found, key=lambda one: (one.module, one.line)))


def _admitted(
    node: ast.Call,
    chain: list[ast.AST],
    function: ast.FunctionDef | ast.AsyncFunctionDef | None,
    keyed: set[ast.AST],
    parents: Mapping[ast.AST, ast.AST],
) -> Admitted:
    if any(one in keyed for one in chain):
        return Admitted.THROUGH_THE_DOOR
    if function is None:
        return Admitted.UNKEYED
    if isinstance(node.func, ast.Attribute) and (
        function.name == node.func.attr and isinstance(parents.get(function), ast.ClassDef)
    ):
        return Admitted.DELEGATES
    if any(
        isinstance(one, ast.Call)
        and _call_name(one) == NO_EFFECT_GUARD
        and one.lineno < node.lineno
        for one in ast.walk(function)
    ):
        return Admitted.NOTHING_TO_KEY
    return Admitted.UNKEYED


def unkeyed_effects(
    ports: Mapping[str, Repeat] = PORTS,
    src: Path = SRC,
    callables: Mapping[str, Repeat] = CALLABLES,
    units: frozenset[str] = EFFECT_UNITS,
) -> tuple[EffectCall, ...]:
    """Every call to a door that issues that nothing admits."""
    return tuple(
        one
        for one in effect_calls(ports, src, callables, units)
        if one.admitted is Admitted.UNKEYED
    )
