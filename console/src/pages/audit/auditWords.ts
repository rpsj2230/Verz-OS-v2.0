/**
 * What an audit entry says, in plain words: what happened, to what, and by whom. No React.
 *
 * **The owner could not read the old column.** Every action was one fragment for every change it
 * covers, so a legal hold placed and one lifted both read "placed or lifted", and a person read as a
 * principal id. Here an entry is named by the change it records: the ledger's triggers write which
 * change it was in `details.change` (or `details.act` for a stop), so "Legal hold lifted" is read off
 * the entry rather than guessed, and an action with no change recorded reads as its own label.
 *
 * **A label is chosen by the product's vocabulary and never by the row's values.** The labels are
 * keyed by `brain.audit.ledger.AuditAction` and `tests/audit-page.test.tsx` holds them to the
 * vocabulary the API document declares, so an action added next month cannot arrive as its code.
 * A change this console has no words for is still readable: its word is spelled with spaces.
 *
 * **People by name, everything else by kind.** The route sends the names of the people on its rows
 * (`brain.people_names`); anything else a row is about is named by its kind, and its identifier is
 * on the subject's own page, in Advanced, because a grant's or a session's id means nothing to a
 * person.
 *
 * Task ids: M27.7.13, M27.16.1
 */

/** What each action records, when the entry names no change of its own. */
export const ACTION_LABELS: Readonly<Record<string, string>> = Object.freeze({
  grant: "Capability granted",
  revoke: "Capability removed",
  deny: "Access refused",
  leash_change: "Agent leash changed",
  entity_merge: "Records merged",
  entity_unmerge: "Merged records separated",
  publish: "Published",
  break_glass: "Emergency access opened",
  compose_change: "Agent's tools or sources changed",
  approval: "Approval decided",
  record_read: "Protected record read",
  browser_session: "Agent browser session",
  sign_in: "Sign-in link changed",
  session_end: "Session ended",
  certification: "Access reviewed",
  credential: "Credential written",
  retention: "Retention sweep changed",
  legal_hold: "Legal hold changed",
  skill: "Skill changed",
  connector: "Source connection changed",
  setting: "Setting changed",
  routing: "Model routing changed",
  instructions: "Agent instructions changed",
  webhook: "Webhook subscriber changed",
  erasure: "Erasure request changed",
  memory: "Memory corrected",
  organisation: "Organisation changed",
  elevation: "Elevation request changed",
  vault_access: "Secrets vault used",
  principal_state: "Sign-in access changed",
  breach: "Breach case changed",
  agent_owner: "Agent handed to a new steward",
  halt: "Work stopped or resumed",
  agent: "Agent changed",
  channel_binding: "Chat account link changed",
  pack: "Capability pack changed",
});

/** The thing an action's change words follow, as in "Legal hold" and then "lifted". */
const CHANGED_THING: Readonly<Record<string, string>> = Object.freeze({
  approval: "Approval",
  certification: "Access review",
  credential: "Credential",
  retention: "Retention sweep",
  legal_hold: "Legal hold",
  skill: "Skill",
  connector: "Source",
  setting: "Setting",
  routing: "Routing",
  instructions: "Instructions",
  webhook: "Webhook subscriber",
  erasure: "Erasure request",
  memory: "Memory",
  elevation: "Elevation request",
  breach: "Breach case",
  agent: "Agent",
  agent_owner: "Agent steward",
  sign_in: "Sign-in link",
  session_end: "Session",
  channel_binding: "Chat account link",
  pack: "Capability pack",
  compose_change: "Agent's tools or sources",
  vault_access: "Secrets vault call",
});

/** Changes that read better as a whole phrase than as the thing and a word. */
const CHANGE_LABELS: Readonly<Record<string, Readonly<Record<string, string>>>> = Object.freeze({
  organisation: Object.freeze({
    joined: "Added to a team",
    left: "Taken out of a team",
    appointed: "Department lead appointed",
    stood_down: "Department lead stood down",
    created: "Department or team created",
    renamed: "Department or team renamed",
    changed: "Department or team changed by hand",
    retired: "Department or team retired",
  }),
  principal_state: Object.freeze({
    disabled: "Sign-in disabled",
    enabled: "Sign-in reinstated",
    created: "Person added to the directory",
  }),
  halt: Object.freeze({ halt: "Work stopped", resume: "Work resumed" }),
  agent_owner: Object.freeze({ owner_changed: "Agent handed to a new steward" }),
});

/** A change word read aloud. */
const CHANGE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  on: "switched on",
  off: "switched off",
  uploaded_again: "uploaded again",
  audience_changed: "offered to a different audience",
});

/** Detail keys that are the entry's own bookkeeping rather than something to show. */
const NOT_SHOWN = new Set(["change", "act", "actor"]);

function spelled(word: string): string {
  return word.replace(/_/g, " ");
}

/** What one entry records, as a short label. */
export function whatWords(action: string, details: Readonly<Record<string, string>> = {}): string {
  const change = details["change"] ?? details["act"];
  if (change !== undefined) {
    const whole = CHANGE_LABELS[action]?.[change];
    if (whole !== undefined) {
      return whole;
    }
    const thing = CHANGED_THING[action];
    if (thing !== undefined) {
      return `${thing} ${CHANGE_WORDS[change] ?? spelled(change)}`;
    }
  }
  return ACTION_LABELS[action] ?? spelled(action);
}

/** Each detail worth showing, as "label: value", in the order the entry holds them. */
export function detailLines(details: Readonly<Record<string, string>>): readonly string[] {
  return Object.entries(details)
    .filter(([key]) => !NOT_SHOWN.has(key))
    .map(([key, value]) => `${spelled(key).replace(/^./, (first) => first.toUpperCase())}: ${value}`);
}

/** Whether a trigger wrote the entry with nobody named, which the row then says. */
export function unattributed(details: Readonly<Record<string, string>>): boolean {
  return details["actor"] === "inferred" || details["actor"] === "unattributed";
}

/** What each kind of subject is called. */
export const SUBJECT_LABELS: Readonly<Record<string, string>> = Object.freeze({
  principal: "Person",
  grant: "Grant",
  agent: "Agent",
  leash: "Agent leash",
  entity: "Record",
  artifact: "Artefact",
  connector: "Source",
  session: "Session",
  credential: "Credential",
  retention: "Retention release",
  legal_hold: "Legal hold",
  skill: "Skill",
  setting: "Setting",
  routing: "Model routing",
  webhook: "Webhook subscriber",
  erasure: "Erasure request",
  memory: "Memory",
  department: "Department",
  scope: "Scope",
  breach: "Breach case",
  halt: "Stop",
  pack: "Capability pack",
});

/** A kind of subject's word, or its code spelled with spaces for a kind this console does not know. */
export function kindWords(kind: string): string {
  return SUBJECT_LABELS[kind] ?? spelled(kind).replace(/^./, (first) => first.toUpperCase());
}

/**
 * A legal hold is named by the reference an administrator typed when placing it, which is the one
 * subject whose id a person chose; every other id is the system's and stays in Advanced.
 */
const NAMED_BY_A_PERSON = new Set(["legal_hold"]);

/** A subject as a row names it: a person by name, a legal hold by its reference, the rest by kind. */
export function subjectWords(kind: string, id: string, people: Readonly<Record<string, string>>): string {
  const person = kind === "principal" ? people[id] : undefined;
  if (person !== undefined) {
    return person;
  }
  return NAMED_BY_A_PERSON.has(kind) ? `${kindWords(kind)} ${id}` : kindWords(kind);
}

/** What a person with no name on this answer reads as: an account the reader has no name for. */
export const NO_NAME = "An account with no name";

/** Who acted, by name, or as the system when a trigger recorded nobody. */
export function actorWords(
  actorId: string,
  people: Readonly<Record<string, string>>,
  details: Readonly<Record<string, string>> = {},
): string {
  return people[actorId] ?? (unattributed(details) ? "The system" : NO_NAME);
}
