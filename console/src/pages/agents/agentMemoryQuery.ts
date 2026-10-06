/**
 * One agent's memory and learning, as `brain.agent_memory_routes` sends them, and the addresses of
 * its two changes.
 *
 * **Read as sent, and absent as absent.** A memory missing its id or its words is left out rather
 * than drawn blank, and `tier_three` null stays null: it means this reader may not be shown where
 * gated changes went, never that there are none. Nothing here counts anything.
 *
 * Task ids: M39.4.1.1, M39.4.1.2, M39.4.1.3, M39.4.1.4, M39.4.1.5, M39.4.2.1, M39.4.2.2, M39.4.2.4
 */

/** Where one agent's memory is asked for, under the API base. */
export function agentMemoryApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/memory`;
}

/** Where one memory is deleted, under the API base. */
export function memoryDeletionApiPath(agentId: string, memoryId: string): string {
  return `${agentMemoryApiPath(agentId)}/${encodeURIComponent(memoryId)}/deletion`;
}

/** Where a learned rule is pressed to promote it, under the API base (M39.4.2.3). */
export function promotionApiPath(memoryId: string): string {
  return `/learning/${encodeURIComponent(memoryId)}/promote`;
}

/** Where a learned rule stands, in words. */
export const PROMOTION_STATE_WORDS: Readonly<Record<string, string>> = {
  held: "held for review",
  awaiting_second: "waiting for a second person",
  promoted: "promoted",
};

/** Where one memory is corrected, under the API base. */
export function memoryEditApiPath(agentId: string, memoryId: string): string {
  return `${agentMemoryApiPath(agentId)}/${encodeURIComponent(memoryId)}/edit`;
}

export interface MemoryItem {
  readonly memoryId: string;
  readonly statement: string;
  readonly confidence: number;
  readonly formedAt: string;
  readonly provenance: string;
  readonly aboutYou: boolean;
  readonly changeable: boolean;
}

export interface MemoryStep {
  readonly memoryId: string;
  readonly replacedId?: string;
  readonly at: string;
  readonly diff: readonly string[];
  readonly trigger?: string;
  readonly correction?: string;
}

export interface TierOneItem {
  readonly memoryId: string;
  readonly change: string;
  readonly controlWrites: string;
  readonly learnedAt: string;
  readonly inEffect: boolean;
  readonly undoOffered: boolean;
}

export interface TierTwoItem {
  readonly memoryId: string;
  readonly change: string;
  readonly evidence: readonly string[];
  readonly promoteReady: boolean;
  readonly learnedAt: string;
  /** Where its learned rule stands; absent for a learning that holds no rule. */
  readonly state?: string;
  /** How many separate conversations would have used it; sent only to whoever may promote it. */
  readonly agreeing?: number;
  readonly promoteOffered: boolean;
}

export interface TierThreeItem {
  readonly memoryId: string;
  readonly department: string;
  readonly backTo: string;
}

export interface AgentMemory {
  readonly curated: readonly MemoryItem[];
  readonly extracted: readonly MemoryItem[];
  readonly aboutYou: readonly MemoryItem[];
  readonly history: readonly MemoryStep[];
  readonly activeTiers: readonly number[];
  readonly tierOne: readonly TierOneItem[];
  readonly tierTwo: readonly TierTwoItem[];
  /** Absent for a reader who may not be shown where gated changes went. */
  readonly tierThree?: readonly TierThreeItem[];
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said`, `listOf` or an exact comparison below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function words(value: unknown): readonly string[] {
  return listOf(value).filter((one): one is string => typeof one === "string");
}

function each<T>(value: unknown, read: (one: Fields) => T | null): T[] {
  return listOf(value)
    .map(fieldsOf)
    .map((one) => (one === null ? null : read(one)))
    .filter((one): one is T => one !== null);
}

function readItem(one: Fields): MemoryItem | null {
  const memoryId = said(one["memory_id"]);
  const statement = said(one["statement"]);
  const formedAt = said(one["formed_at"]);
  const confidence = one["confidence"];
  if (memoryId === undefined || statement === undefined || formedAt === undefined || typeof confidence !== "number") {
    return null;
  }
  return {
    memoryId,
    statement,
    formedAt,
    confidence,
    provenance: said(one["provenance"]) ?? "",
    aboutYou: one["about_you"] === true,
    changeable: one["changeable"] === true,
  };
}

function readStep(one: Fields): MemoryStep | null {
  const memoryId = said(one["memory_id"]);
  const at = said(one["at"]);
  if (memoryId === undefined || at === undefined) {
    return null;
  }
  const replacedId = said(one["replaced_id"]);
  const trigger = said(one["trigger"]);
  const correction = said(one["correction"]);
  return {
    memoryId,
    at,
    diff: words(one["diff"]),
    ...(replacedId === undefined ? {} : { replacedId }),
    ...(trigger === undefined ? {} : { trigger }),
    ...(correction === undefined ? {} : { correction }),
  };
}

/** The memory out of a body, or null when the body is not an object at all. */
export function readAgentMemory(payload: unknown): AgentMemory | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const tierThree = fields["tier_three"];
  return {
    curated: each(fields["curated"], readItem),
    extracted: each(fields["extracted"], readItem),
    aboutYou: each(fields["about_you"], readItem),
    history: each(fields["history"], readStep),
    activeTiers: listOf(fields["active_tiers"]).filter((one): one is number => Number.isInteger(one)),
    tierOne: each(fields["tier_one"], (one) => {
      const memoryId = said(one["memory_id"]);
      const change = said(one["change"]);
      const learnedAt = said(one["learned_at"]);
      if (memoryId === undefined || change === undefined || learnedAt === undefined) {
        return null;
      }
      return {
        memoryId,
        change,
        learnedAt,
        controlWrites: said(one["control_writes"]) ?? "",
        inEffect: one["in_effect"] === true,
        undoOffered: one["undo_offered"] === true,
      };
    }),
    tierTwo: each(fields["tier_two"], (one) => {
      const memoryId = said(one["memory_id"]);
      const change = said(one["change"]);
      const learnedAt = said(one["learned_at"]);
      if (memoryId === undefined || change === undefined || learnedAt === undefined) {
        return null;
      }
      const state = said(one["state"]);
      const agreeing = typeof one["agreeing"] === "number" ? one["agreeing"] : undefined;
      return {
        memoryId,
        change,
        learnedAt,
        evidence: words(one["evidence"]),
        promoteReady: one["promote_ready"] === true,
        promoteOffered: one["promote_offered"] === true,
        ...(state === undefined ? {} : { state }),
        ...(agreeing === undefined ? {} : { agreeing }),
      };
    }),
    ...(Array.isArray(tierThree)
      ? {
          tierThree: each(tierThree, (one) => {
            const memoryId = said(one["memory_id"]);
            const department = said(one["department"]);
            const backTo = said(one["back_to"]);
            return memoryId === undefined || department === undefined || backTo === undefined ? null : { memoryId, department, backTo };
          }),
        }
      : {}),
  };
}

/** Where a memory came from, in words: `brain.console.reach_view.Provenance`'s two. */
export const PROVENANCE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  curated: "Stated by a person",
  extracted: "Inferred from how they asked",
});
