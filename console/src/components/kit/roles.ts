/**
 * The platform's six roles, as the words a person reads, from one list.
 *
 * `brain.identity.roles.Role` is the vocabulary: compiled in, six members, never rows. The console
 * had its own spelling of it inside `pages/access/PersonName.tsx`, which a page of the kit cannot
 * import without pointing the kit at a page, and which nothing checked against the Python. This is
 * that table, moved to where the kit can reach it, and `tests/empty-lists.test.tsx` reads
 * `roles.py` and holds the two together, so a seventh role added there fails here before a screen
 * says "ask a Seventh role".
 *
 * **A role is a word the empty-list sentence uses and nothing more.** A role grants no capability
 * (`brain.identity.roles.NO_ROLE_IMPLIES_A_CAPABILITY`), so naming one here is naming who the screen
 * is designed for, which `brain.console.screens.Screen.intended_for` records, and never a statement
 * that holding the role is what lets a person press the button. The sentence says so in its own
 * words (`EmptyList`), and the grant decides.
 *
 * Task ids: M27.15.69
 */

/** The six platform roles, by the ids `brain.identity.roles.Role` gives them. */
export const PLATFORM_ROLES = [
  "super_admin",
  "department_admin",
  "member",
  "auditor",
  "connector_admin",
  "approver",
] as const;

export type PlatformRole = (typeof PLATFORM_ROLES)[number];

/** A role's word as a person reads it. */
export const ROLE_WORDS: Readonly<Record<PlatformRole, string>> = Object.freeze({
  super_admin: "Super Admin",
  department_admin: "Department admin",
  member: "Member",
  auditor: "Auditor",
  connector_admin: "Connector admin",
  approver: "Approver",
});

/** A role's word, or the API's own spelling of one this console has not heard of. */
export function roleWords(role: string): string {
  return (ROLE_WORDS as Readonly<Record<string, string>>)[role] ?? role;
}
