/**
 * Who an agent is offered to beside its level, as `brain.agent_audience_routes` sends it.
 *
 * **Read as sent, and absent as absent.** The departments and people beside the level reach the
 * agent's steward and a holder of the lifecycle authority only, so for anybody else the lists are
 * empty and `namesShown` is false, and this file derives nothing from that: it never turns an empty
 * list into a sentence saying nobody was named, which would be a statement the reader was not told.
 * The refusal sentence is the route's, drawn only for a reader the route sent one to.
 *
 * **The acts are two posts.** Offering is `POST /agents/{id}/audience/additions` and withdrawing is
 * `POST /agents/{id}/audience/removals`, each with the kind and the one word that names a department
 * or a person. Both answer with the view again, so the card is what the install now holds.
 *
 * Task ids: M27.11.13
 */

export type OfferKind = "department" | "person";

/** Where one agent's audience is read, under the API base. */
export function agentAudienceApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/audience`;
}

/** Where an agent is offered to one more department or person, under the API base. */
export function agentOfferApiPath(agentId: string): string {
  return `${agentAudienceApiPath(agentId)}/additions`;
}

/** Where an offer is withdrawn, under the API base. */
export function agentWithdrawApiPath(agentId: string): string {
  return `${agentAudienceApiPath(agentId)}/removals`;
}

export interface AgentAudienceView {
  readonly agentId: string;
  readonly level: string;
  readonly department?: string;
  readonly ownerId: string;
  /** Whether this reader was told the names beside the level at all. */
  readonly namesShown: boolean;
  readonly departments: readonly string[];
  readonly people: readonly string[];
  readonly mayChange: boolean;
  /** Why the offers cannot be changed, sent only to a reader who answers for the agent. */
  readonly refusal?: string;
  /** Every department an offer may name, sent only to a reader who may change the offers. */
  readonly departmentChoices: readonly string[];
  readonly words: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read back
  // through `said`, `listOf` or an exact comparison below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function wordsOf(value: unknown): readonly string[] {
  return Array.isArray(value)
    ? (value as readonly unknown[]).map(said).filter((one): one is string => one !== undefined)
    : [];
}

/** The audience out of a body, or null when it is not one. */
export function readAudience(payload: unknown): AgentAudienceView | null {
  const fields = fieldsOf(payload);
  const agentId = said(fields?.["agent_id"]);
  const level = said(fields?.["level"]);
  const ownerId = said(fields?.["owner_id"]);
  const words = said(fields?.["words"]);
  if (fields === null || agentId === undefined || level === undefined || ownerId === undefined || words === undefined) {
    return null;
  }
  const department = said(fields["department"]);
  const refusal = said(fields["refusal"]);
  return {
    agentId,
    level,
    ownerId,
    words,
    namesShown: fields["names_shown"] === true,
    departments: wordsOf(fields["departments"]),
    people: wordsOf(fields["people"]),
    mayChange: fields["may_change"] === true,
    departmentChoices: wordsOf(fields["department_choices"]),
    ...(department === undefined ? {} : { department }),
    ...(refusal === undefined ? {} : { refusal }),
  };
}

/** The body an offer or a withdrawal sends: the kind and the one word that names it. */
export function offerBody(kind: OfferKind, value: string): { readonly kind: OfferKind; readonly value: string } {
  return { kind, value: value.trim() };
}
