"""The audit ledger: hash-chained, append-only, and deliberately incurious.

Two failures this module exists to prevent.

**A ledger nobody can trust.** A table that is append-only by convention is one UPDATE
away from saying whatever the person holding the database password wants it to say, and
nothing about the table afterwards reveals that it happened. So each entry carries a
digest over its own fields *and* over the previous entry's digest. Editing entry 12
invalidates 12 and every entry after it, and checking that is a walk rather than an act
of faith.

**A ledger that is itself the leak.** The audit trail is the longest-retained and most
widely read table in the system, which makes it the worst possible place to keep anything
sensitive. Two rules follow, and both are enforced in the model rather than left to
callers, because a check that lives in a helper is a check someone can construct their way
around:

- an entry records `ent_hash`, never the capability list. A ledger of capabilities is a
  map of who can see what, which is a document nobody should have;
- an entry records field *names*, never field *values*. `redact_details` is how a caller
  gets from one to the other.

What the chain does not prove, stated plainly because a hash chain is routinely credited
with more than it does:

- **Tail truncation.** Delete the newest three entries and what remains verifies
  perfectly. Nothing inside the data can close that. Only a digest recorded outside the
  database can, which is what `head` produces and `covers_anchor` checks.
- **Wholesale rewriting.** Anyone able to rewrite every row from the tamper point forward
  produces a chain that verifies. The chain proves nothing was *quietly* edited; the
  external anchor is what makes a rewrite visible.

Scope: M24.1 is the chain logic only. Nothing here touches a database. The table that
eventually persists these entries stores the same fields and runs `verify` as its check
job (M24.1.2).

Task ids: M24.1.1, M24.1.2, M24.1.3, M24.1.4, M24.2.1, M42.6.5, M27.7.21, M27.11.1
"""

from __future__ import annotations

import enum
import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from brain.core.entitlement import CAPABILITY_RE, VERBS

# --------------------------------------------------------------------- grammars

#: What a field name looks like: `contract_value`, `client.contract_value`. This is the
#: field half of the capability grammar in brain.core.entitlement, on purpose: the names
#: the ledger is allowed to record are exactly the names a grant can be written about.
FIELD_NAME = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$"

#: A reference, not prose. No whitespace, bounded length. Real ids in this system are
#: mixed case (`recuA1B2C3` from Lark, `c_0447` from Laravel), so case cannot be part of
#: the rule.
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"

#: db.py sizes trace_id at 64 characters; app.py mints them as a uuid4 hex, which is 32.
TRACE_ID = r"^[A-Za-z0-9_.-]{1,64}$"

#: EntitlementSet.ent_hash truncates its sha256 to 32 characters. If that ever changes,
#: this fails loudly on the next entry written rather than silently storing a short hash.
ENT_HASH = r"^[0-9a-f]{32}$"

#: A full sha256 hexdigest: the chain links.
DIGEST = r"^[0-9a-f]{64}$"

_FIELD_NAME_RE = re.compile(FIELD_NAME)
#: 32 hex (an ent_hash) or 64 hex (a chain digest). Both are safe to record as a detail
#: value; see `_is_recordable` for why a digest is not treated as a value.
_RECORDABLE_DIGEST_RE = re.compile(r"^[0-9a-f]{32}(?:[0-9a-f]{32})?$")
_IDENTIFIER_RE = re.compile(IDENTIFIER)

#: Domain separation, and a warning. Every digest begins with this string, so a digest
#: produced here can never collide with one produced by some other hashing in the system.
#: If the set of hashed fields ever changes, this constant must change with it, and at
#: that moment every historical entry stops verifying. A chain cannot be re-hashed in
#: place without destroying the one thing it was built to prove, so changing the covered
#: fields means storing a schema version per entry and teaching `verify` both. It is a
#: migration, not an edit to this line.
HASH_SCHEMA = "brain.audit.v1"

#: sha256 hexdigest width. Genesis is the same width as every other link so that nothing
#: in `verify` has to special-case the first entry.
DIGEST_CHARS = 64
GENESIS_HASH = "0" * DIGEST_CHARS

#: What a stripped value becomes. It deliberately carries no type and no length. A marker
#: reading `<redacted:int:5>` would tell any reader the order of magnitude of the salary
#: underneath, which is most of what the salary was worth hiding; the shape of a value is
#: still information about the value.
REDACTED = "<redacted>"

#: The things an audit entry can be *about*. Closed, because the client-visible audit view
#: filters on this (M24.1.5), and a free-text subject kind makes "everything that ever
#: happened to this principal" unanswerable without a full scan and a guess.
SUBJECT_KINDS = frozenset(
    {
        "principal",
        "grant",
        "agent",
        "leash",
        "entity",
        "artifact",
        "connector",
        "session",
        # A vault slot a credential was written into, since 2026-09-16. See CREDENTIAL below.
        "credential",
        # A release of the retention sweep, and a legal hold, since 2026-09-16. See RETENTION and
        # LEGAL_HOLD below.
        "retention",
        "legal_hold",
        # A skill in the library, since 2026-09-17. See SKILL below.
        "skill",
        # A row of `ops.setting`, a rung of the routing matrix and a webhook subscriber, since
        # 2026-09-17. See SETTING, ROUTING and WEBHOOK below.
        "setting",
        "routing",
        "webhook",
        # A request to erase somebody's data, since 2026-09-17. See ERASURE below.
        "erasure",
        # A memory a correction marked, since 2026-09-17. See MEMORY below.
        "memory",
        # A department with its teams, and a scope, since 2026-09-17. See ORGANISATION below.
        "department",
        "scope",
        # A suspected personal-data breach, since 2026-09-21. See BREACH below.
        "breach",
    }
)


class AuditAction(enum.StrEnum):
    """Everything that must reach the ledger (M24.1.3).

    Closed on purpose. An open action vocabulary is how an auditable event ends up
    unaudited: someone adds a code path, invents a string for it, and nothing anywhere
    notices that no entry was ever written. Adding a member here fails the invariant test
    that pins this set, which is the point - a new auditable action becomes a deliberate
    edit in two places rather than an omission in one.

    DENY and REVOKE are separate members although the delivery document names them
    together as one item. A deny is a request refused at runtime; a revoke is a grant
    taken away by an administrator. They have different actors, they differ by orders of
    magnitude in frequency (denies are routine, revokes are rare), and they answer
    different questions. Collapsing them makes "who removed her access, and when"
    unanswerable without reading the details of every refusal in between.

    COMPOSE_CHANGE was added on 2026-09-08, and it is the eighth. M39.1.1.3 asks for an
    attachment added to or removed from an agent to reach the ledger with who, when and why,
    and there was nothing to write it under. The same absence blocked two other things:
    `migrations/versions/0004` records that an audit trigger on `ops.setting` could not be
    written for want of a member, and `brain.connectors.registry` returns a lifecycle event
    for a caller to record with nothing covering it either.

    Recording it under an existing member was rejected, and `brain.tables.audit` has the
    precedent that made it tempting: `PACK_ASSIGNMENT_ACTION` is `GRANT`, because a pack
    assignment really is somebody gaining capabilities. That is exactly why GRANT cannot take
    this: its justification is that "what did this person gain, and when" is answerable from
    one action, and filling it with rows about which tools an agent carries breaks the query
    it exists to serve. PUBLISH is about an artefact; LEASH_CHANGE's whole content is its two
    rungs. No member fitted, so the honest answer was a member.

    APPROVAL was added on 2026-09-09, and it is the ninth. M40.6.1.2 asks that approving,
    rejecting and amending each reach the ledger, and M33.6.1.3 adds taking the work over.
    Nothing covered any of them: `brain.gate.leash.SuspendedAction` records the decision on
    its own row, which answers "what happened to this one" and not "what has this approver
    been waving through", and the second question is the one an auditor asks.

    **One member for four verdicts, and the asymmetry with `ApprovalState` is deliberate.**
    A state says whether the stored action may still run and there are three of those; a
    verdict says what the person did and there are four. Taking the work over and rejecting
    both leave the agent's action unrun, so they are one state and two verdicts, and adding
    states for them would produce two members every consumer has to know both of. The verdict
    rides in the details, which is where a closed vocabulary that is finer than the action's
    belongs: `revoke` already carries its reason code the same way.

    Eight characters, well inside the column's sixteen. `approval_decision` is nineteen and
    would not have fitted, which is the constraint `COMPOSE_CHANGE` ran into first.

    RECORD_READ was added on 2026-09-10, and it is the tenth. Needs Rupash item 45 chose to
    answer "which agents have read my HR record" for a narrow set (M40.4.2.4), and that
    question had no member at all: `brain.member_activity.member_notes` reported it as
    unanswerable, and the item describes this list as eight members, which it stopped being
    the day before when `approval` landed. Count the enum rather than the paragraph.

    **This member breaks the shape of the list, and that is the decision rather than the
    count.** Every one of the nine above records a change to what somebody may do. A read
    changes nothing: it is the first member that records something happening *within* the
    permissions rather than to them, and admitting one is admitting that the ledger is no
    longer only a record of authority. The narrowness of `brain.audit.reads.WRITTEN_DOWN` is
    what keeps that admission proportionate, and if that set ever grows to everything, this
    member is the thing to argue about again.

    It goes in the ledger anyway because there is nowhere else it can go. A read log that can
    be edited proves nothing, and this is the only append-only, hash-chained, tamper-evident
    store here; the trace holds no row identity and is kept a month, and the payload store
    holds content and is kept thirty days. Recording it under an existing member was rejected
    for the reason `COMPOSE_CHANGE` gives against GRANT: DENY is a refusal and a read that
    succeeded is not one, PUBLISH is an artefact leaving, BREAK_GLASS is an authorisation, and
    filling any of them breaks the query it exists to serve.

    Eleven characters. `read` alone was rejected as a value rather than as a length: the
    ledger records reads of a declared set of records and not every read in the system, and a
    member called `read` invites exactly the reading this one is not.

    **Adding one moves no existing digest.** `compute_entry_hash` takes the action per entry
    and `HASH_SCHEMA` is a literal, so an unused member is invisible to every hash already
    written and every chain still verifies. What it does need is a migration, because
    `brain.tables.audit` renders the CHECK constraint from this enum and `0002` wrote the
    list out literally; `0022` supersedes it in the way `0007`, `0011` and `0012` already
    supersede each other for the channel vocabulary. The migration must land before code
    writes the new action, or a write fails at the database rather than in a test.

    SIGN_IN was added on 2026-09-15, and it is the eleventh. `brain.identity.sign_in_binding`
    binds a Keycloak subject to a principal, and `auth.principal_identity` has no column saying
    who did it, so "who gave this account a way in as her, and when" had nowhere to be
    answered. **It is recorded by the database, from a trigger, the way a grant is**, because
    a binding written by an operator's statement is exactly as much a way in as one written
    by the console, and a caller that has to remember to audit forgets during an incident.

    Recording it as GRANT was the tempting precedent and was rejected for the reason
    COMPOSE_CHANGE gives: `PACK_ASSIGNMENT_ACTION` is GRANT because a pack assignment really
    is capabilities gained, and a binding gains no capability. It decides which person a
    token is, and "what did this person gain" filled with rows about accounts breaks the
    query GRANT serves. One member for both directions, bound and retired, with the change
    in the details, for the reason APPROVAL carries its verdict there. Seven characters.

    SESSION_END was added on 2026-09-16, and it is the twelfth. M27.7.10 puts a control on the
    Sessions screen that ends somebody's sign-in, because revoking a grant does not close one,
    and `auth.session` records when a session stopped and why but not who stopped it. "Who
    ended her session, and when" had nowhere to be answered. **Recorded by the database, from
    a trigger on `auth.session`, the way SIGN_IN is**, so the disable cascade `0003` runs is
    recorded as well as a press of the console's control, and an operator ending one by hand
    is recorded without having to remember to be.

    Recording it as REVOKE was the tempting precedent and was rejected for COMPOSE_CHANGE's
    reason: a revoke is a grant taken away, "what did this person lose" is the query it serves,
    and ending a session takes away no grant at all, which is the whole reason the control
    exists. SIGN_IN was rejected too: it is about which account is a person, and a session is
    one sitting of that account. The subject is the principal, so the person whose session it
    was can read that it was ended, and the reason rides in the details as a closed word. The
    session id is not in the entry, because it is not a field name and would be stored as the
    marker. Eleven characters.

    CERTIFICATION was added on 2026-09-16, and it is the thirteenth. M27.7.9 puts an access review
    on a screen, and a lead deciding that a grant stands had nothing to be recorded under: a kept
    grant changes no row the grant trigger watches, so "who looked at this and kept it, and when"
    was a question the ledger could not answer. **Recorded by the database, from a trigger on
    `gate.review_decision`**, the way SIGN_IN and SESSION_END are, so a decision inserted by an
    operator's statement is recorded as well as one pressed in the console.

    Every existing member was tried. GRANT answers "what did this person gain" and a kept grant
    gains nothing; REVOKE is a grant taken away, and a removal already writes one from the grant
    trigger, so recording the decision under it as well would be two revokes for one lost
    capability; APPROVAL is a suspended action decided and a grant under review is not suspended.
    One member for both decisions, keep and remove, with the decision in the details, for the
    reason APPROVAL carries its verdict there. The subject is the grant, as the grant trigger
    writes it for a direct row and a pack assignment alike. Thirteen characters.

    CREDENTIAL was added on 2026-09-16, and it is the fourteenth. `brain.ops.credentials` puts a
    provider key into the vault from the console and from the setup wizard, and "who replaced
    the key every question is sent with, and when" was answered by a log line, which is kept for
    a month and can be edited by whoever holds the log. **Recorded by the database, from a
    trigger on `ops.credential_write`**, the way SIGN_IN, SESSION_END and CERTIFICATION are, so a
    row written by an operator's statement is recorded as well as one the application writes.

    Every existing member was tried. COMPOSE_CHANGE is what an agent carries and a provider key
    belongs to no agent; GRANT and REVOKE are capabilities, and a key confers none on anybody.
    The subject kinds were tried too, and `connector` is the near miss: a connector is a source
    this system reads, and a model provider is not one, so filing a key under it would put
    provider keys into every answer to "what happened to our sources". So a member, and a kind
    beside it named for what is written to, a vault slot. **Never the value**: not its length,
    a prefix or a fingerprint, for the
    reason `brain.credential_routes` gives against answering with any of them, and the entry
    carries no details at all because nothing about a write is left once the value is taken
    out. The subject is the slot's path with its slashes written as dots,
    `credential:providers.anthropic`, which `brain.audit.record.credential_subject_id` argues.
    Ten characters.

    RETENTION and LEGAL_HOLD were added on 2026-09-16, and they are the fifteenth and sixteenth.
    `brain.retention_routes` releases the retention sweep so its next run deletes, withdraws that
    release, places a legal hold that suspends deletion and lifts one, and each wrote a row and
    nothing else: "who let the sweep delete, and who took the hold off first" had no
    tamper-evident answer, and those are the two questions asked after data is found to be gone.
    **Recorded by the database, from triggers on `ops.retention_release` and `obs.legal_hold`**,
    the way CREDENTIAL is, on the insert and on the one update that marks a release withdrawn or a
    hold lifted, with the actor read off the row's own column so nothing is inferred.

    Every existing member was tried. GRANT and REVOKE are capabilities, and neither write changes
    what anybody may do; APPROVAL is a suspended action decided, and the sweep is not suspended but
    unreleased; CERTIFICATION is a grant reviewed. **Two members rather than one**, because a
    release lets data go and a hold keeps it, and an auditor asking one of those questions should
    not read the other's rows. One member for both directions of each, with the change in the
    details, for the reason SIGN_IN gives. Nine and ten characters.

    **And two subject kinds, because no existing kind names either object.** `principal` was the
    near miss for a hold, which names people as its subjects and actors, and it was rejected: a
    hold can name everybody at once, and one entry per named person would copy the hold's lists
    into the ledger, which is a map of whose data is under legal hold, kept longest and read most
    widely. So the subject is the object itself, which has a start and an end:
    `retention:<release id>` for a release, released and then withdrawn, and `legal_hold:<hold id>`
    for a hold, placed and then lifted, so everything that happened to one is one subject. A hold's
    id is an identifier its placer chose and `obs.legal_hold` keeps for as long as the chain, so
    the subject discloses nothing the hold's own row does not.

    SKILL was added on 2026-09-17, and it is the seventeenth. `brain.skill_routes` adds a skill
    to the library from an uploaded or pasted package, and a second person approves or rejects
    it, and until then nothing stored an imported skill at all. "Who put this procedure in front
    of our agents, and who read it before it could run" is the question asked after an agent
    does something nobody expected, and it had no tamper-evident answer. **Recorded by the
    database, from triggers on `agent.skill` and `agent.skill_review`**, the way CERTIFICATION
    is, so a row an operator inserts by hand is recorded as well as one the console writes.

    Every existing member was tried. COMPOSE_CHANGE is what one agent carries, and a skill in
    the library is attached to nobody until it is assigned, which is recorded under
    COMPOSE_CHANGE by `0056`'s third trigger; CERTIFICATION is a grant reviewed, and a skill
    confers no grant, which is the whole of `brain.tools.skills`; APPROVAL is a suspended
    action decided, and an imported skill is not an action; PUBLISH is an artefact an agent
    produced. One member for its three changes, imported, approved and rejected, with the
    change in the details, for the reason APPROVAL carries its verdict there. The subject is
    the skill's name, so every version of one procedure is one subject, and the digest of the
    bytes the change was about rides in the details: a skill's digest is over its whole text,
    which is not an enumerable input, so it is recordable for `_is_recordable`'s reason about a
    digest rather than refused as a value. Five characters.

    CONNECTOR was added on 2026-09-17, and it is the eighteenth. The Connectors screen connects a
    source from the console and disconnects one (M42.6.5), and "who let this system read our
    finance ledger, and who stopped it" is the question an auditor asks about a source, answered
    until then by nothing: `brain.connectors.registry` returned a lifecycle event for somebody to
    record and there was no member to record it under, which `COMPOSE_CHANGE`'s paragraph above
    already said. **Recorded by the database, from a trigger on `ops.connector_connection`**, the
    way CREDENTIAL is, on the insert and on the one update that marks a connection disconnected,
    with the actor read off the row's own column for that change.

    Every existing member was tried. CREDENTIAL records the key being written, and a connection
    writes one, so connecting a source leaves both entries: the key under `credential:` and the
    decision to read the source under `connector:`. Filing the second under CREDENTIAL would put
    a disconnect, which writes no key, under a member whose whole content is a key written.
    COMPOSE_CHANGE is what one agent carries, and a connected source is the install's rather than
    an agent's; GRANT and REVOKE are capabilities, and connecting a source grants nobody anything,
    which is `brain.connectors.registry`'s own first sentence. The subject kind `connector` has
    existed since `0002` with nothing written under it, and
    `brain.identity.staff_sync.AUDIT_KIND_DECISIONS` already decides who reads it. One member for
    both directions, with the change in the details, for the reason SIGN_IN gives. Nine
    characters.

    SETTING, ROUTING, INSTRUCTIONS and WEBHOOK were added on 2026-09-17, and they are the
    nineteenth to the twenty-second. M27.8.17 follows every console write to the audit entry it
    leaves, and five kinds of write left none: switching a feature, pausing, resuming or running a
    scheduled job, editing an agent's instructions or giving them back, saving a rung of the
    routing matrix, and registering a webhook subscriber, replacing its signing secret or
    switching it off. Each was attributed on its own row and nowhere else, so "who switched
    prompt editing on", "who paused the retention sweep" and "who pointed our identifiers at that
    address" had a last answer and no history. `0004` had recorded the settings half as a gap for
    want of exactly these two words. **Each is recorded by the database, from a trigger on the
    row's own table**, `0059`'s, so a statement an operator types is recorded as well as a press in
    the console.

    Every existing member was tried, and one was tried for all five. GRANT and REVOKE are
    capabilities, and none of these writes changes what anybody may do. COMPOSE_CHANGE is an
    attachment added to or removed from an agent, and `brain.prompt_routes` already argued that an
    instruction edit is not one: nothing is attached, the agent's own text changes. LEASH_CHANGE's
    whole content is its two rungs, and a routing rung is a model deployment's place in a chain,
    not an agent's autonomy, so filing one under the other would put model timeouts into every
    answer to "who loosened this agent". CREDENTIAL was the near miss for a replaced webhook
    secret, which is a vault write: it was rejected because the subscriber's change is what an
    auditor of where identifiers are sent reads, and a credential entry beside it would be the same
    event twice. CONNECTOR, added the same day, is a source this system reads from, and a
    subscriber is somewhere it sends to; "who let us read the finance ledger" and "who pointed our
    events at that address" are asked by different people. One member covering all five was
    rejected for RETENTION and LEGAL_HOLD's reason: an auditor asking who pointed the company's
    identifiers at an address should not read model timeouts, and one asking who edited what an
    agent is told should not read job pauses.

    **Why SETTING is one member for features, jobs and every other setting, rather than three.**
    They are one table and one act, a knob turned, and the trigger that records them is one
    function over `ops.setting` that cannot tell a feature from a pause without restating
    `brain.ops.features` and `brain.ops.schedule_control` in SQL. The subject is the key, so
    `setting:feature.prompt_editing` and `setting:schedule.paused.retention_sweep` say which knob,
    and the change is `switched_on` or `switched_off` for a boolean and `set` for anything else,
    because a boolean has two values and carries no content while every other value might. **Never
    the value.** A run requested is `set` and not its instant, and a company name typed into the
    wizard is `set` and not the name.

    **INSTRUCTIONS is about the agent, under the `agent` kind, and needs no kind of its own**,
    because an agent is exactly what `agent` names and a department's head already reads that kind
    for the leash changes and compositions of their people. The change is `edited` or
    `given_back`, and the digest of the configuration put in force rides in the details, which is
    the hash the answer cache keys on, so the entry says which configuration without saying what
    it says. ROUTING's subject is the rung, and its details name the columns that moved and never
    their values. WEBHOOK's subject is the subscriber, and its change is
    `brain.tables.webhook_change.WebhookChange`'s word. Seven, seven, twelve and seven characters.

    **And three subject kinds.** `setting`, because no kind names a row of configuration;
    `routing`, because a rung is neither an agent nor a connector; `webhook`, because a subscriber
    is an address the company's identifiers are sent to and `connector`, the near miss, is a
    source this system reads. `brain.identity.staff_sync.AUDIT_KIND_DECISIONS` decides for each
    whether a department head reads it, and none of the three is a head's.

    ERASURE was added on 2026-09-17, and it is the twenty-third. The Retention and erasure screen
    files a request to erase one person's data and the worker carries it out across every store it
    can reach (M27.7.24). "Who asked for her data to be erased, and what did that do" is asked
    after the data is found to be gone, and the removals themselves answer only part of it: a
    retired grant writes a `revoke` from `0003`'s trigger and nothing else says why. **Recorded by
    the database, from a trigger on `ops.erasure_request`**, the way LEGAL_HOLD is, on the insert
    and on the one update that marks the request finished, with the actor read off the row's own
    column for that change.

    Every existing member was tried. RETENTION is the sweep released to delete by age, and an
    erasure is one person's data removed on a request, whatever its age; LEGAL_HOLD keeps data
    rather than letting it go; REVOKE is a grant taken away, which an erasure causes and is not.
    One member for the request and its outcome, with the change in the details, for the reason
    SIGN_IN gives. **The subject is the request, never the person**: `erasure:<request id>`, for
    the reason LEGAL_HOLD's subject is the hold, because a list of the people who asked to be
    erased is a list of endings, and the ledger is the table kept longest and read most widely.
    Seven characters.

    MEMORY was added on 2026-09-17, and it is the twenty-fourth. The Learning screen undoes a
    tier-one learning (M27.7.21), and an undo writes a correction that changes what the system
    recalls from then on: "who decided the system should stop believing this, and when" is the
    question asked the day an answer changes and nobody can say why. **Recorded by the database,
    from a trigger on `mem.correction`**, the way CONNECTOR is, on the insert, with the actor read
    off the row's own `recorded_by` and the correction's kind in the details. A correction row is
    never updated, so there is nothing else to fire on.

    Every existing member was tried. REVOKE is a grant taken away, and an undo takes nobody's access
    away: a tier-one learning never changed who may see what, which is the definition of tier one in
    `brain.memory.tiers`. COMPOSE_CHANGE is what one agent carries, and a learning belongs to a
    memory rather than to an agent's composition, and may belong to no agent at all. APPROVAL is a
    suspended action decided, and a tier-one learning was never suspended. The subject is the memory
    the correction marked, under a new kind `memory`, because the only other candidate, the agent,
    is absent from a learning formed in a plain conversation and would file an undo under a party
    that did not make it. The details are the kind of correction and nothing else: never the
    statement, which is `brain.memory.correction`'s refusal to keep a transcript in a correction
    log, and never the memory that replaced it, which the row keeps. Six characters.

    ORGANISATION was added on 2026-09-17, and it is the twenty-fifth. The Departments and teams
    screen places a person in a team and takes them out, and appoints a department's lead and
    stands one down (M27.7.4), and the staff directory sync does both where its source is trusted
    to say where somebody sits. "Who put her in the design team" and "who made him lead of sales"
    had no answer anywhere, because until then no table held either fact. **Recorded by the
    database, from triggers on `gate.team_membership` and `gate.department_lead`**, the way
    CONNECTOR is, on the insert and on the one update that ends a row.

    Every existing member was tried. GRANT and REVOKE are capabilities, and a membership and a lead
    confer none, which is `brain.console.organisation`'s whole argument about both: filing a
    placement under GRANT would put a row that widens nobody into every answer to "who gave her
    access". CERTIFICATION is a grant reviewed. SIGN_IN is an identity bound. One member for the
    four changes, joined, left, appointed and stood down, with the team's path or the department's
    slug in the details, because both are where somebody sits and an auditor asking one question
    asks the other. **The subject is the person, `principal:<id>`**, rather than a new kind for a
    team, so everything that happened to somebody's place in the organisation is on their own
    subject, and `brain.identity.staff_sync.AUDIT_KIND_DECISIONS` already decides who reads it.
    Twelve characters.

    ELEVATION was added on 2026-09-17, and it is the twenty-sixth. The Elevation requests screen
    lets somebody ask for a capability they do not hold, for a stated reason and a few hours, and
    lets somebody else approve or deny it (M27.7.8). "Who asked for more, and who let them have
    it" is the question after an incident, and it had no answer. **Recorded by the database, from
    a trigger on `gate.elevation_request`**, on the insert and on the one update that decides it.
    An approval also writes a grant row, whose own GRANT entry `0003`'s trigger appends as it does
    for every grant.

    Every existing member was tried, and BREAK_GLASS was the near miss. It is an authorisation,
    and `brain.console.elevation.chain_findings` holds that a BREAK_GLASS entry in the main chain
    is the separate chain collapsed into a name: the database has one ledger, so a trigger writing
    BREAK_GLASS into it is that finding by construction. GRANT is the reach given, which the grant
    row already records, and a request or a denial gives nothing; APPROVAL is a suspended action
    decided, and a request for more access is not an agent's action. One member for the three
    changes, requested, approved and denied, with the capability and the reason code in the
    details, and the requester as the subject. Nine characters.

    **ORGANISATION widened on 2026-09-17 to the structure the placements sit in, with no new
    member.** The Departments and teams screen creates, renames and retires departments and their
    teams, and creates and retires the scopes grants are written over (M27.11.1), and until then no
    table under those acts had a trigger: `gate.department`, `gate.team` and `gate.scope` were
    written by hand, by the demo seed and by furnishing, and "who retired finance, and who made the
    scope our contractors are granted over" had no answer at all. **Recorded by the database, from
    `0086`'s triggers on the three tables**, on the insert, on a rename, on any other column moved
    by hand, and on retirement.

    A member of its own was tried and rejected. The act is organising, which is what this member
    already records: an auditor asking who put her in the design team asks next who made the design
    team, and splitting the two would put them in two filters. GRANT and REVOKE were the near miss
    for a scope and are wrong for the reason ORGANISATION's first paragraph gives about a placement:
    a scope confers nothing until a grant names it, and a grant written over one records its own
    GRANT. What changes is the subject, and so **two subject kinds**: `department:<slug>`, for a
    department and each of its teams, whose path rides in the details as it does on a placement, so
    everything that happened to a department and its parts is one subject; and `scope:<slug>`, for a
    scope, because a scope over a named set of departments belongs to none of them. The subject is
    the slug rather than the row id, because the slug is the value every grant's predicate carries,
    so a department retired and created again under the same name is the same history to anybody
    asking what reached it.
    """

    GRANT = "grant"
    DENY = "deny"
    REVOKE = "revoke"
    LEASH_CHANGE = "leash_change"
    ENTITY_MERGE = "entity_merge"
    PUBLISH = "publish"
    BREAK_GLASS = "break_glass"
    #: An agent's composition changed: a skill, a knowledge predicate, a connector or a
    #: channel attached or detached. Fourteen characters, which matters because the column
    #: is `VARCHAR(16)`: `attachment_change` and `agent_config_change` were the other two
    #: candidates and neither fits.
    COMPOSE_CHANGE = "compose_change"
    #: A person decided a suspended action: approved it, rejected it, took the work over or
    #: approved an amended version. The verdict is in the details, for the reason above.
    APPROVAL = "approval"
    #: A record in `brain.audit.reads.WRITTEN_DOWN` was read, and shown. Never every read:
    #: the declared set is two entries and `record_read` refuses anything outside it.
    RECORD_READ = "record_read"
    #: A Keycloak subject was bound to a principal, or a binding was retired. Which of the two
    #: is in the details. Written by `0047`'s trigger on `auth.principal_identity`.
    SIGN_IN = "sign_in"
    #: A sign-in session was ended before it lapsed: from the console, by a disable or by a
    #: retirement. Why is in the details. Written by `0050`'s trigger on `auth.session`.
    SESSION_END = "session_end"
    #: A grant under access review was kept or removed by somebody other than its holder. Which
    #: of the two is in the details. Written by `0052`'s trigger on `gate.review_decision`.
    CERTIFICATION = "certification"
    #: A credential was written into a vault slot. The slot is the subject and there are no
    #: details, because the value is the only other thing a write has. Written by `0054`'s
    #: trigger on `ops.credential_write`.
    CREDENTIAL = "credential"
    #: The retention sweep was released to delete, or a release was withdrawn. Which is in the
    #: details. Written by `0054`'s trigger on `ops.retention_release`.
    RETENTION = "retention"
    #: A legal hold was placed or lifted. Which is in the details, and never whom it names.
    #: Written by `0054`'s trigger on `obs.legal_hold`.
    LEGAL_HOLD = "legal_hold"
    #: A skill was added to the library, or approved or rejected by somebody other than whoever
    #: added it. Which is in the details, with the digest of the bytes it was about. Written by
    #: `0056`'s triggers on `agent.skill` and `agent.skill_review`.
    SKILL = "skill"
    #: A source was connected from the console, or disconnected. Which is in the details, and
    #: never its settings or its key. Written by `0057`'s trigger on `ops.connector_connection`.
    CONNECTOR = "connector"
    #: A row of `ops.setting` was switched, set or retired: a feature, a job's pause or run
    #: request, or any other setting. Which is in the details, and never the value. Written by
    #: `0059`'s trigger on `ops.setting`.
    SETTING = "setting"
    #: A rung of the routing matrix was added, changed or retired. The columns that moved are in the
    #: details, and never their values. Written by `0059`'s trigger on `ops.routing_rung`.
    ROUTING = "routing"
    #: An agent's instructions were edited or given back to its template, with the digest of the
    #: configuration put in force. Written by `0059`'s trigger on `agent.template_instance`.
    INSTRUCTIONS = "instructions"
    #: A webhook subscriber was registered, had its signing secret replaced, or was switched off.
    #: Written by `0059`'s trigger on `ops.webhook_change`.
    WEBHOOK = "webhook"
    #: A request to erase somebody's data was filed, or the queue finished it: erased, held or
    #: incomplete. Which is in the details, and never whose data it was. Written by `0060`'s
    #: trigger on `ops.erasure_request`.
    ERASURE = "erasure"
    #: A memory was marked by a correction: superseded by another, or demoted. Which is in the
    #: details, and never what either memory says. Written by `0061`'s trigger on `mem.correction`.
    MEMORY = "memory"
    #: A person was placed in a team or taken out of one, or appointed to lead a department or
    #: stood down. Which is in the details, with the team's path or the department's slug. Written
    #: by `0062`'s triggers on `gate.team_membership` and `gate.department_lead`. Since `0086`, also
    #: a department, a team or a scope created, renamed, changed by hand or retired, written by the
    #: triggers on `gate.department`, `gate.team` and `gate.scope` under its own subject.
    ORGANISATION = "organisation"
    #: Somebody asked for a capability they do not hold, or somebody else approved or denied the
    #: request. Which is in the details, with the capability and the reason code. Written by
    #: `0062`'s trigger on `gate.elevation_request`.
    ELEVATION = "elevation"
    #: The secrets vault answered a call about a slot: a key read or written, its metadata read, a
    #: run token minted or revoked, or the vault's own configuration changed. Which operation, which
    #: part of the slot, whether it was refused and the token's HMAC are in the details, and never a
    #: value. Written by `0093`'s trigger on `ops.vault_access`, which the worker fills from the
    #: vault's audit log (`brain.ops.vault_audit_ship`).
    #:
    #: **A member of its own, and the second that records something within the permissions rather
    #: than a change to them**, after RECORD_READ. `credential` was the tempting home and is the
    #: wrong one for GRANT's reason: "when was the Anthropic key last replaced" is answered from
    #: that action alone, and filling it with every read the worker makes would bury the answer.
    #: The actor is the vault, `secrets_vault`, because the principal behind a token is not in the
    #: log; the HMAC in the details ties calls by one token together without naming it.
    VAULT_ACCESS = "vault_access"
    #: A person was disabled, or enabled again. Which is in the details. Written by `0095b`'s
    #: trigger on `auth.principal`, one entry per change of `disabled_at` between set and unset,
    #: so restoring somebody's access is on the record as surely as taking it away. Fifteen
    #: characters, inside the column's sixteen. Not `session_end`, which is about one sitting:
    #: a disable with no session open ends none, and an enable ends none ever.
    PRINCIPAL_STATE = "principal_state"
    #: A suspected personal-data breach was opened, assessed, notified to the Commission or to the
    #: people in it, excused from telling them, or closed. Which is in the details, and never what
    #: happened, whose data it was or how many. Written by `0104`'s trigger on `ops.breach_case`,
    #: so the clock the regulator asks about has its own record of who moved it and when.
    BREACH = "breach"
    #: An agent's owner changed: somebody accepted an agent whose owner the staff sync marked as
    #: having left, or any other statement moved `agent.agent.owner_id`. The owner before and after
    #: are in the details. Written by `0105`'s trigger on `agent.agent`, so a change made at a
    #: prompt is recorded as surely as one made from the Staff sources screen. Eleven characters.
    #: Not `publish`, which is an artefact, and not `compose_change`, which is what an agent
    #: carries: who answers for an agent is neither, and "who took over the agent that did this"
    #: is the question asked after it did something nobody expected (M1.8.9).
    AGENT_OWNER = "agent_owner"


# --------------------------------------------------------------------- redaction


def _is_recordable(value: str) -> bool:
    """True when a details value is a name, a comma-joined list of names, a digest, or
    the redaction marker.

    A digest is admitted where a raw value is not, and the difference is enumerability.
    An `ent_hash` is a sha256 over a whole grant set: the input space is large enough that
    the digest reveals nothing. A digest of a five-digit salary is a different object
    entirely, because ninety thousand candidates is a lookup table, not a secret. That is
    why this admits digests by *shape* only where the producer is known to be an
    entitlement set or the chain itself, and why `changed_fields` records names rather
    than hashing the values it compares.
    """
    if value == REDACTED:
        return True
    if _RECORDABLE_DIGEST_RE.match(value):
        return True
    if _is_capability(value):
        # A named exception, decided on 5 September, rather than a loosening of the rule.
        #
        # The strict version was defensible and unusable: an audit view that cannot say
        # *what* was granted is not an audit view, and "Aaron granted Wei Ling something"
        # is not a sentence anyone can act on. A capability is not personal data, it names
        # a permission rather than a person or a value, and it is already legible in the
        # grant table to anyone who can read this ledger.
        #
        # The exception is narrow on purpose. It admits the capability grammar and nothing
        # adjacent to it, so a value cannot arrive disguised as one: the grammar is a known
        # verb, a colon, and dotted lowercase names, with no spaces and no digits.
        return True
    return all(_FIELD_NAME_RE.match(part) for part in value.split(","))


def _is_capability(value: str) -> bool:
    """A capability string, by the same grammar the rest of the system uses.

    Imported rather than copied. Two definitions of one grammar drift, and the drift here
    would be silent in the direction that matters: a ledger admitting a shape the
    capability type rejects is a ledger admitting something that is not a capability.

    The verb is checked as well as the shape, so `notice:the_client_is_overdue` does not
    slip through by happening to look like one.
    """
    if not CAPABILITY_RE.match(value):
        return False
    return value.split(":", 1)[0] in VERBS


def _redact_value(value: object) -> str:
    if isinstance(value, bool):
        # There are exactly two booleans, so neither can carry content.
        return "true" if value else "false"
    if isinstance(value, str):
        return value if _is_recordable(value) else REDACTED
    if isinstance(value, Mapping):
        # A nested mapping is a record. Keep the names of its fields, drop everything
        # else: this is what makes a before/after state recordable at all (M24.1.4).
        names = sorted(k for k in value if isinstance(k, str) and _FIELD_NAME_RE.match(k))
        return ",".join(names) if names else REDACTED
    if isinstance(value, Sequence):
        # All-or-nothing. A list where one element is a value must not half-survive: the
        # surviving half tells the reader which element was the interesting one.
        items = [v for v in value if isinstance(v, str) and _FIELD_NAME_RE.match(v)]
        return ",".join(sorted(items)) if items and len(items) == len(value) else REDACTED
    return REDACTED


def redact_details(details: Mapping[str, object]) -> dict[str, str]:
    """Reduce a details mapping to names and digests, and nothing that could be a value.

    This is an allowlist, and that is the whole design. A denylist of things that look
    like values ("contains spaces", "looks like money", "matches an email") is unbounded:
    for every rule written, some real value eventually slips past, and the failure is
    silent and permanent because the ledger is never deleted. An allowlist of things that
    look like *field names* is closed, and the cost of getting it wrong is a redacted
    entry rather than a leaked one.

    Survives redaction: a field name, a digest, a bool, a sequence of field names
    (comma-joined), and a mapping (reduced to the field names among its keys). Everything
    else becomes `REDACTED`.

    A key that is not itself a field name is dropped rather than redacted, because in that
    case the key is the leak: `{"SNM Construction Pte Ltd": "overdue"}` gives away the
    client by naming it, and redacting only the value would keep the name.
    """
    return {
        key: _redact_value(value) for key, value in details.items() if _FIELD_NAME_RE.match(key)
    }


def changed_fields(before: Mapping[str, object], after: Mapping[str, object]) -> tuple[str, ...]:
    """The names of the fields whose values differ. Names only; never the values.

    The delivery document asks an entry to carry "before and after state" (M24.1.4). This
    is as much of that as the ledger is allowed to hold, and the gap is deliberate rather
    than an oversight. Recording the values would put every salary and every contract
    value into the longest-retained table in the system. Recording a digest of them is
    worse than it first sounds, for the reason given in `_is_recordable`: a low-entropy
    value and its digest are the same secret.

    So the ledger proves *that* a field changed, when, and who changed it, and the row's
    own version history says what it changed to. Two records, two different retentions,
    two different access controls; joining them is a deliberate act that leaves its own
    audit entry.
    """
    missing = object()
    names = set(before) | set(after)
    return tuple(
        sorted(
            name
            for name in names
            if _FIELD_NAME_RE.match(name) and before.get(name, missing) != after.get(name, missing)
        )
    )


# --------------------------------------------------------------------- hashing


def _digest(parts: Iterable[str]) -> str:
    """Length-prefixed concatenation, then sha256.

    The prefix is not decoration. Joining parts with a separator makes the digest
    ambiguous the moment any part can contain that separator: `("ab", "c")` and
    `("a", "bc")` join to the same string, so two different entries share a digest and one
    can be swapped for the other without the chain noticing. Prefixing each part with its
    length removes the ambiguity outright, rather than resting on a promise that no actor
    id, subject or detail key will ever contain the separator character.
    """
    joined = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def compute_entry_hash(
    *,
    seq: int,
    at: datetime,
    actor_id: str,
    action: AuditAction,
    subject: str,
    ent_hash: str,
    trace_id: str,
    details: Mapping[str, str],
    prev_hash: str,
) -> str:
    """The digest an entry carries. Covers every field, and the previous entry's digest.

    Public because whatever persists these rows has to be able to recompute them without
    reconstructing an `AuditEntry` first.
    """
    # The order of these lines is part of the hash schema. Reordering them changes every
    # digest the system has ever produced; see HASH_SCHEMA.
    parts: list[str] = [
        HASH_SCHEMA,
        prev_hash,
        str(seq),
        # Normalised to UTC so that one instant written as +08:00 and as Z digests
        # identically. Two workers in different timezones recording the same event must
        # not disagree about it.
        at.astimezone(UTC).isoformat(),
        actor_id,
        action.value,
        subject,
        ent_hash,
        trace_id,
    ]
    # Sorted, because a dict preserves insertion order and two entries with identical
    # details built in different orders would otherwise digest differently. This is the
    # same mistake EntitlementSet.ent_hash avoids by sorting its grants before hashing.
    for key in sorted(details):
        parts.append(key)
        parts.append(details[key])
    return _digest(parts)


# --------------------------------------------------------------------- the entry


class AuditEntry(BaseModel):
    """One fact, chained to the one before it.

    `entry_hash` is stored rather than computed on read. A computed property would follow
    the data wherever it went, so an altered entry would produce an altered digest and
    agree with itself forever. Storing the digest is what makes disagreement possible, and
    the disagreement is the detection.

    The model does not check `entry_hash` on construction, which reads like an omission
    and is not. A tampered row has to load so that `AuditChain.verify` can *report* it. A
    validator here would raise on load instead, and a ledger that refuses to load its own
    damaged rows cannot tell anybody which row is damaged, or what it says.

    `frozen=True` stops attributes being rebound; it does not stop `entry.details["k"]`
    being written in place, since the value is a real dict. That is acceptable precisely
    because nothing here depends on immutability: `verify` recomputes rather than trusting,
    so an in-place edit is caught in the same breath as an edit to any other field.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int = Field(ge=0)
    at: datetime
    actor_id: str = Field(pattern=IDENTIFIER)
    action: AuditAction
    subject: str = Field(min_length=3, max_length=160)
    #: The actor's entitlement at the time, as a hash. Never the capabilities themselves.
    ent_hash: str = Field(pattern=ENT_HASH)
    trace_id: str = Field(pattern=TRACE_ID)
    details: dict[str, str] = Field(default_factory=dict)
    prev_hash: str = Field(pattern=DIGEST)
    entry_hash: str = Field(pattern=DIGEST)

    @field_validator("at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            msg = "at must be timezone-aware; a naive timestamp is a silent bug"
            raise ValueError(msg)
        return v

    @field_validator("subject")
    @classmethod
    def _subject_grammar(cls, v: str) -> str:
        kind, sep, ident = v.partition(":")
        if not sep or kind not in SUBJECT_KINDS:
            msg = f"subject {v!r} must be <kind>:<id>, kind one of {sorted(SUBJECT_KINDS)}"
            raise ValueError(msg)
        if not _IDENTIFIER_RE.match(ident):
            msg = f"subject id {ident!r} is not an identifier; a subject is a reference, not prose"
            raise ValueError(msg)
        return v

    @field_validator("details")
    @classmethod
    def _names_only(cls, v: dict[str, str]) -> dict[str, str]:
        """Refuse anything `redact_details` would have stripped.

        This duplicates the redactor deliberately. `AuditChain.append` always redacts, but
        entries also arrive by being loaded from a table, and a row written by an older
        version of the code, by a migration, or by hand must not be able to introduce a
        value that the redactor would have caught. Enforcing it at the type means there is
        one answer to "can a value be in the ledger" rather than one answer per code path.
        """
        bad: list[str] = []
        for key, value in v.items():
            if not _FIELD_NAME_RE.match(key):
                bad.append(f"key {key!r} is not a field name")
            elif not _is_recordable(value):
                bad.append(f"value of {key!r} is not a name, a digest or {REDACTED}")
        if bad:
            msg = "details would put a value in the ledger: " + "; ".join(bad)
            raise ValueError(msg)
        return v

    def recompute_hash(self) -> str:
        """What this entry's digest should be, given what it currently says."""
        return compute_entry_hash(
            seq=self.seq,
            at=self.at,
            actor_id=self.actor_id,
            action=self.action,
            subject=self.subject,
            ent_hash=self.ent_hash,
            trace_id=self.trace_id,
            details=self.details,
            prev_hash=self.prev_hash,
        )


# --------------------------------------------------------------------- breakage


class BreakReason(enum.StrEnum):
    """Why the walk stopped.

    The verification job (M24.1.2) reports this alongside the index, because "the chain
    broke at 47" with no reason sends an operator to read forty-seven rows by hand to work
    out whether they are looking at a tamper, a bad migration or a deletion.
    """

    SEQUENCE_BROKEN = "sequence_broken"
    LINK_BROKEN = "link_broken"
    CONTENT_ALTERED = "content_altered"


class ChainBreak(BaseModel):
    """Where the chain stopped holding, and what was expected there instead."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    seq: int
    reason: BreakReason
    expected: str
    actual: str


# --------------------------------------------------------------------- legal hold


class LegalHold(BaseModel):
    """A predicate that suspends deletion (M24.2.1).

    A predicate rather than a flag on the row, for one reason: a hold is placed before
    anyone knows which entries it will need to cover, and it has to cover entries written
    *after* it is placed. A flag can only mark what already exists, so a flag-based hold
    quietly fails to hold exactly the entries a live dispute is generating.

    `reason_code` is a field-name token and not free text. A free-text reason on a legal
    hold is where the names of the parties, the complainant and the allegation end up, in
    the one table that outlives every retention policy in the system.

    A released hold is marked released, never deleted: which entries were held, on whose
    authority and for how long is itself a thing that gets asked about later.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=IDENTIFIER)
    reason_code: str = Field(pattern=FIELD_NAME, max_length=80)
    subjects: frozenset[str] = frozenset()
    actors: frozenset[str] = frozenset()
    #: A company-wide hold. Explicit, because the alternative reading of "no subjects and
    #: no actors" is "everything", and a hold that means everything by accident is as bad
    #: as one that means nothing by accident.
    all_subjects: bool = False
    placed_at: datetime
    released_at: datetime | None = None

    @field_validator("placed_at", "released_at")
    @classmethod
    def _tz_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            msg = "hold timestamps must be timezone-aware; a naive one is a silent bug"
            raise ValueError(msg)
        return v

    def model_post_init(self, _context: object, /) -> None:
        if not (self.all_subjects or self.subjects or self.actors):
            # The failure this prevents: a hold is placed, the sweep runs, and nothing is
            # held, because the hold names nothing and nothing complains. It is discovered
            # when the data is asked for and is gone.
            msg = "a hold must name subjects or actors, or set all_subjects"
            raise ValueError(msg)

    def is_active(self, now: datetime | None = None) -> bool:
        moment = now or datetime.now(UTC)
        if moment < self.placed_at:
            return False
        return self.released_at is None or moment < self.released_at

    def covers(self, entry: AuditEntry) -> bool:
        """Whether this hold reaches the entry. Says nothing about whether it is active."""
        return self.all_subjects or entry.subject in self.subjects or entry.actor_id in self.actors


def is_held(entry: AuditEntry, holds: Iterable[LegalHold], now: datetime | None = None) -> bool:
    """True when any active hold reaches this entry. A held entry cannot be deleted."""
    return any(hold.is_active(now) and hold.covers(entry) for hold in holds)


# --------------------------------------------------------------------- the chain


class AuditChain:
    """An ordered run of entries, and the walk that proves nothing in it moved.

    `start_hash` exists so that a *window* of a longer ledger can be verified on its own.
    A verification job that can only ever start from genesis is a job that gets slower
    every day and is eventually switched off; one that can verify last month against the
    digest it recorded last month is one that keeps running. It is also what makes a
    retention prune leave something that still verifies rather than something that looks
    like a forgery.
    """

    def __init__(
        self, entries: Sequence[AuditEntry] = (), *, start_hash: str = GENESIS_HASH
    ) -> None:
        self._entries: list[AuditEntry] = list(entries)
        self._start_hash = start_hash

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    @property
    def start_hash(self) -> str:
        return self._start_hash

    def __len__(self) -> int:
        return len(self._entries)

    def head(self) -> str:
        """The digest to record outside the database.

        An empty chain's head is its start hash, so an anchor taken before the first entry
        is still meaningful and nothing has to special-case the empty case.
        """
        return self._entries[-1].entry_hash if self._entries else self._start_hash

    def append(
        self,
        *,
        action: AuditAction,
        actor_id: str,
        subject: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
        details: Mapping[str, object] | None = None,
    ) -> AuditEntry:
        """Write one entry and return it.

        `seq`, `prev_hash` and `entry_hash` are computed here and are not parameters. A
        caller who can choose them can forge a link, and there is then no such thing as a
        well-formed entry, only a conventional one.

        `at` has no default, and `datetime.now(UTC)` is deliberately not one. db.py makes
        the argument in full: application time is the clock of whichever container handled
        the write, those clocks drift, and a ledger ordered by them is subtly wrong exactly
        when the ordering matters. The caller must pass one authoritative clock's reading.
        Note the consequence, which is real: because the timestamp is inside the digest,
        the database cannot fill it in with `server_default` the way every other table
        here does. Either the caller reads the clock from the database and passes it in, or
        the digest has to be computed in the database.

        Details are redacted here so that no caller has to remember to.
        """
        seq = self._entries[-1].seq + 1 if self._entries else 0
        prev_hash = self.head()
        safe_details = redact_details(details or {})
        entry = AuditEntry(
            seq=seq,
            at=at,
            actor_id=actor_id,
            action=action,
            subject=subject,
            ent_hash=ent_hash,
            trace_id=trace_id,
            details=safe_details,
            prev_hash=prev_hash,
            entry_hash=compute_entry_hash(
                seq=seq,
                at=at,
                actor_id=actor_id,
                action=action,
                subject=subject,
                ent_hash=ent_hash,
                trace_id=trace_id,
                details=safe_details,
                prev_hash=prev_hash,
            ),
        )
        self._entries.append(entry)
        return entry

    def first_break(self) -> ChainBreak | None:
        """The first entry that does not hold, with the reason, or None."""
        previous_hash = self._start_hash
        previous_seq: int | None = None
        for index, entry in enumerate(self._entries):
            # Sequence first. It is redundant with the link check for a deletion, since
            # both catch it, but it names the failure: "seq jumped from 4 to 6" reads as a
            # missing row, where "digest mismatch" reads as a tamper, and an operator
            # follows those two findings to different places.
            if previous_seq is not None and entry.seq != previous_seq + 1:
                return ChainBreak(
                    index=index,
                    seq=entry.seq,
                    reason=BreakReason.SEQUENCE_BROKEN,
                    expected=str(previous_seq + 1),
                    actual=str(entry.seq),
                )
            if entry.prev_hash != previous_hash:
                return ChainBreak(
                    index=index,
                    seq=entry.seq,
                    reason=BreakReason.LINK_BROKEN,
                    expected=previous_hash,
                    actual=entry.prev_hash,
                )
            recomputed = entry.recompute_hash()
            if recomputed != entry.entry_hash:
                return ChainBreak(
                    index=index,
                    seq=entry.seq,
                    reason=BreakReason.CONTENT_ALTERED,
                    expected=recomputed,
                    actual=entry.entry_hash,
                )
            previous_hash = entry.entry_hash
            previous_seq = entry.seq
        return None

    def verify(self) -> int | None:
        """The index of the first entry that does not hold, or None when the chain is
        whole. Index rather than sequence number, because a window's indices are what
        address the entries the caller is holding."""
        found = self.first_break()
        return None if found is None else found.index

    def covers_anchor(self, *, seq: int, entry_hash: str) -> bool:
        """True when this chain still contains the anchored entry, unchanged.

        `verify` alone cannot see a truncated tail: remove the newest entries and what is
        left is a valid chain that ends earlier. Nothing inside the data distinguishes
        that from a ledger where those events never happened. The only fix is a digest
        recorded somewhere the database administrator does not control - by the
        verification job, in a separate store, or published - and asked for later. This is
        the asking.
        """
        for entry in self._entries:
            if entry.seq == seq:
                return entry.entry_hash == entry_hash
        return False

    def prune_before(
        self,
        cutoff: datetime,
        *,
        holds: Iterable[LegalHold] = (),
        now: datetime | None = None,
    ) -> tuple[AuditChain, tuple[AuditEntry, ...]]:
        """Remove the oldest entries retention has released, stopping at the first it has
        not. Returns the retained chain and what was removed.

        A retention sweep over a hash chain can only ever take a prefix. Removing an entry
        from the middle leaves the next one pointing at a digest that is no longer there,
        so the chain reports a break for the rest of its life and the sweep has destroyed
        the only property the ledger existed for. The sweep therefore walks from the oldest
        entry and stops dead at the first that is either newer than the cutoff or under
        legal hold. One held entry from three years ago pins every entry after it, which is
        expensive and is the correct behaviour: that is what a hold is.

        The retained chain carries the last removed entry's digest as its `start_hash`, so
        what remains still verifies as a window instead of looking like a chain whose
        beginning was forged.

        This returns a new chain rather than mutating, so a sweep that is going to refuse
        can be inspected before anything is written back.
        """
        held = list(holds)
        cut = 0
        for entry in self._entries:
            if entry.at >= cutoff or is_held(entry, held, now):
                break
            cut += 1
        removed = tuple(self._entries[:cut])
        start = removed[-1].entry_hash if removed else self._start_hash
        return AuditChain(self._entries[cut:], start_hash=start), removed
