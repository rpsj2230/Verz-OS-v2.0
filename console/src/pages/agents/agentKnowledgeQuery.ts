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

import { UPLOADS_API_PATH, uploadPath, type UploadLevel } from "../knowledgeQuery";
import type { Clause } from "./agentCapabilitiesQuery";

/** How many documents one page asks for. The next page is asked for by offset. */
export const PAGE_SIZE = 25;

/** Where one agent's Knowledge section is asked for, under the API base. */
export function agentKnowledgeApiPath(agentId: string, offset = 0): string {
  return `/agents/${encodeURIComponent(agentId)}/knowledge?limit=${String(PAGE_SIZE)}&offset=${String(offset)}`;
}

/**
 * Where a file is added from this page: the Knowledge page's own address and query, under the agent,
 * so what the query says (closed-list words and a department slug, never a name) has one author.
 */
export function agentKnowledgeUploadApiPath(agentId: string, kind: string, level: UploadLevel, department: string): string {
  return `/agents/${encodeURIComponent(agentId)}/knowledge/uploads${uploadPath(kind, level, department).slice(UPLOADS_API_PATH.length)}`;
}

/** Where a web page is added from this page. The address travels in the body, never the query. */
export function agentKnowledgeLinkApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/knowledge/links`;
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
  /** Whether this reader may replace it with a newer version, as the Knowledge page decides it. */
  readonly canReplace: boolean;
  readonly reached: boolean;
}

export interface AgentKnowledge {
  readonly items: readonly KnowledgeItem[];
  readonly rule: readonly Clause[];
  readonly canAdd: boolean;
  /** The department the rule already draws on, where an addition lands unless another is chosen. */
  readonly addInto?: string;
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
    canReplace: one["can_replace"] === true,
    // Absent means reached: the list is the documents the rule reaches, so a body that omits the
    // field is the list's own contract and not a document left out.
    reached: one["reached"] !== false,
  };
}

function readRule(value: unknown): Clause[] {
  return each(value, (clause) => {
    const field = said(clause["field"]);
    const op = said(clause["op"]);
    const text = said(clause["value"]);
    return field === undefined || op === undefined || text === undefined ? null : { field, op, value: text };
  });
}

/** What adding from this page answers: the document, and whether the agent draws on it. */
export interface KnowledgeAdded {
  readonly itemId: string;
  readonly title: string;
  readonly route: string;
  readonly reached: boolean;
  readonly said: string;
  readonly blocking: readonly Clause[];
  readonly canWiden: boolean;
}

/** The answer to an addition, or null when the body is not one. */
export function readKnowledgeAdded(payload: unknown): KnowledgeAdded | null {
  const fields = fieldsOf(payload);
  const itemId = said(fields?.["item_id"]);
  const text = said(fields?.["said"]);
  if (fields === null || itemId === undefined || text === undefined) {
    return null;
  }
  return {
    itemId,
    title: said(fields["title"]) ?? itemId,
    route: said(fields["route"]) ?? "",
    reached: fields["reached"] === true,
    said: text,
    blocking: readRule(fields["blocking"]),
    canWiden: fields["can_widen"] === true,
  };
}

/** The Knowledge section out of a body, or null when the body is not an object at all. */
export function readAgentKnowledge(payload: unknown): AgentKnowledge | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const unread = said(fields["unread"]);
  const addInto = said(fields["add_into"]);
  return {
    items: each(fields["items"], readKnowledgeItem),
    rule: readRule(fields["rule"]),
    canAdd: fields["can_add"] === true,
    ...(addInto === undefined ? {} : { addInto }),
    more: fields["more"] === true,
    atLeast: fields["at_least"] === true,
    keptRule: said(fields["kept_rule"]) ?? "",
    ...(unread === undefined ? {} : { unread }),
  };
}
