/**
 * One agent's Knowledge section, as `brain.agent_knowledge_routes` sends it, and the address it is
 * asked at. No React.
 *
 * **Read as sent, and absent as absent.** An item missing its id or its title is left out rather
 * than drawn blank; a verifier is named only where the API named one; `unread` is the one sentence
 * the API answers with when it cannot say which documents the agent draws on. **Nothing here counts
 * anything**: the list is the reader's own documents the agent's rule reaches, a longer page is a
 * second request and never a pass over a list the browser holds, and `more` says only that a page
 * is full.
 *
 * Task ids: M39.9.1.1, M39.9.1.6
 */

import type { Clause } from "./agentCapabilitiesQuery";

/** How many documents one page asks for. The next page is asked for by offset. */
export const PAGE_SIZE = 25;

/** Where one agent's Knowledge section is asked for, under the API base. */
export function agentKnowledgeApiPath(agentId: string, offset = 0): string {
  return `/agents/${encodeURIComponent(agentId)}/knowledge?limit=${String(PAGE_SIZE)}&offset=${String(offset)}`;
}

export interface KnowledgeItem {
  readonly itemId: string;
  readonly title: string;
  readonly kindLabel: string;
  readonly place: string;
  readonly level: string;
  readonly addedBy: string;
  readonly addedByName: string;
  readonly addedAt?: string;
  readonly verification: string;
  readonly verifiedByName?: string;
  readonly verifiedAt?: string;
  readonly reviewBy?: string;
  readonly due: boolean;
  readonly reached: boolean;
}

export interface AgentKnowledge {
  readonly items: readonly KnowledgeItem[];
  readonly rule: readonly Clause[];
  readonly canAdd: boolean;
  readonly more: boolean;
  readonly atLeast: boolean;
  /** Set when the API could not say which documents the agent draws on, with an empty list. */
  readonly unread?: string;
  readonly keptRule: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `listOf` or a type test below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function each<T>(value: unknown, read: (one: Fields) => T | null): T[] {
  return listOf(value)
    .map(fieldsOf)
    .map((one) => (one === null ? null : read(one)))
    .filter((one): one is T => one !== null);
}

function optional<K extends string>(key: K, value: string | undefined): Partial<Record<K, string>> {
  return value === undefined ? {} : ({ [key]: value } as Record<K, string>);
}

/** One document out of a body, or null when it names no document or no title. */
export function readKnowledgeItem(one: Fields): KnowledgeItem | null {
  const itemId = said(one["item_id"]);
  const title = said(one["title"]);
  if (itemId === undefined || title === undefined) {
    return null;
  }
  return {
    itemId,
    title,
    kindLabel: said(one["kind_label"]) ?? "Not recorded",
    place: said(one["place"]) ?? "",
    level: said(one["level"]) ?? "",
    addedBy: said(one["added_by"]) ?? "",
    addedByName: said(one["added_by_name"]) ?? "",
    ...optional("addedAt", said(one["added_at"])),
    verification: said(one["verification"]) ?? "unverified",
    ...optional("verifiedByName", said(one["verified_by_name"])),
    ...optional("verifiedAt", said(one["verified_at"])),
    ...optional("reviewBy", said(one["review_by"])),
    due: one["due"] === true,
    // Absent means reached: the list is the documents the rule reaches, so a body that omits the
    // field is the list's own contract and not a document left out.
    reached: one["reached"] !== false,
  };
}

/** The Knowledge section out of a body, or null when the body is not an object at all. */
export function readAgentKnowledge(payload: unknown): AgentKnowledge | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const unread = said(fields["unread"]);
  return {
    items: each(fields["items"], readKnowledgeItem),
    rule: each(fields["rule"], (clause) => {
      const field = said(clause["field"]);
      const op = said(clause["op"]);
      const value = said(clause["value"]);
      return field === undefined || op === undefined || value === undefined ? null : { field, op, value };
    }),
    canAdd: fields["can_add"] === true,
    more: fields["more"] === true,
    atLeast: fields["at_least"] === true,
    keptRule: said(fields["kept_rule"]) ?? "",
    ...(unread === undefined ? {} : { unread }),
  };
}
